"""Host evaluator and paused, isolated actors sharing a live wiki."""
from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
import json
from pathlib import Path
import random
import subprocess

from parabox.model import Client, assistant_message, parse_args
from parabox.sandbox import Box, Limits
from parabox.util import now, save, sha256
from parabox.workspace import read_regular, snapshot_regular, write_regular

from . import fixture


def deadline_time(value: str) -> datetime:
    result = datetime.fromisoformat(value)
    if result.tzinfo is None:
        raise ValueError("Deadline must include a timezone")
    return result


def require_time(deadline: str) -> None:
    if datetime.now(timezone.utc) >= deadline_time(deadline):
        raise RuntimeError("Execution deadline reached")


class SharedBox(Box):
    def start(self):
        subprocess.run(self.run_argv(), check=True, capture_output=True, timeout=30)

    def freeze(self):
        subprocess.run(["podman", "pause", self.name], check=True, capture_output=True, timeout=15)

    def thaw(self):
        subprocess.run(["podman", "unpause", self.name], check=True, capture_output=True, timeout=15)

    def stop(self):
        removal_error = None
        try:
            subprocess.run(["podman", "rm", "-f", "--time", "0", self.name],
                           capture_output=True, timeout=15)
        except (OSError, subprocess.SubprocessError) as error:
            removal_error = repr(error)
        result = subprocess.run(["podman", "container", "exists", self.name],
                                capture_output=True, timeout=10)
        if result.returncode != 1:
            raise RuntimeError(f"Unverified container shutdown: {self.name}; {removal_error}")


def archive(meta: Path, raw: bytes) -> str:
    digest = sha256(raw)
    destination = meta / "artifacts" / digest
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not destination.exists():
        destination.write_bytes(raw)
    return digest


def wiki_state(directory: Path, meta: Path) -> dict:
    return {name: archive(meta, raw) for name, raw in snapshot_regular(directory).items()}


def capture(workspace: Path, meta: Path, target: list[int]) -> tuple[bytes, dict]:
    try:
        raw = read_regular(workspace, "submission.json", limit=65536)
    except (OSError, ValueError) as error:
        return b"", {"sha256": None, "length": None, "read_error": type(error).__name__,
                     "feedback": {"error": "Invalid submission file"}}
    record = {"sha256": archive(meta, raw), "feedback": fixture.evaluate(raw, target)}
    try:
        value = json.loads(raw)
        record["length"] = len(value) if isinstance(value, list) else None
    except (ValueError, UnicodeError, RecursionError):
        record["length"] = None
    return raw, record


def truncated_response(value) -> bool:
    if isinstance(value, dict):
        return any((key in ("finish_reason", "finishReason") and item in ("length", "MAX_TOKENS"))
                   or (isinstance(item, (dict, list)) and truncated_response(item))
                   for key, item in value.items())
    if isinstance(value, list):
        return any(truncated_response(item) for item in value)
    return False


class Actor:
    def __init__(self, directory, spec, config, target, image, wiki, deadline, guard=None):
        self.directory, self.spec, self.target = Path(directory), spec, target
        self.deadline = deadline
        self.guard = guard
        self.workspace, self.meta = self.directory / "workspace", self.directory / "meta"
        self.directory.mkdir(parents=True, exist_ok=False)
        self.workspace.mkdir()
        self.scoring = spec["scoring"]
        self.submission_limit = 3 if self.scoring == "mean" else 1
        files = fixture.participant_files(spec["prefix"], target, self.scoring)
        for name, raw in files.items():
            write_regular(self.workspace, name, raw)
        (self.workspace / "shared/wiki").mkdir(parents=True)
        (self.workspace / "shared/submissions").mkdir(parents=True)
        self.receipts = wiki.parent / "submissions"
        self.receipts.mkdir(exist_ok=True)
        self.messages = [{"role": "system", "content": fixture.SYSTEM},
                         {"role": "user", "content": fixture.assignment(self.scoring)}]
        self.tools = fixture.tools(self.scoring)
        save(self.meta / "prompts.json", {"messages": self.messages, "tools": self.tools,
                                         "files": {name: raw.decode() for name, raw in files.items()}})
        save(self.meta / "spec.json", spec)
        self.box = SharedBox("costly-information-" + sha256(str(self.directory.resolve()))[:20],
                             self.workspace, image, Limits(cpus="2", memory="2g"),
                             mounts=((str(wiki), "/workspace/shared/wiki", "rw,z"),
                                     (str(self.receipts), "/workspace/shared/submissions", "ro,z")))
        self.config, self.client = config, None
        self.pending = deque()
        self.used = self.tests = self.turns = 0
        self.scores, self.public_receipts = [], []
        self.submitted = self.finished = False
        self.error = self.feedback = self.end_reason = None
        self.stopped = {"verified": False}
        self.response_failures = self.phase_rejections = 0
        self.evaluations, self.snapshots = [], []
        self.started_at = now()
        self.capture()

    def capture(self):
        raw, record = capture(self.workspace, self.meta, self.target)
        self.snapshots.append(record)
        return raw, record

    def check_execution(self):
        require_time(self.deadline)
        if self.guard is not None:
            self.guard()
        require_time(self.deadline)

    def start(self):
        self.check_execution()
        self.box.start()
        self.box.freeze()

    def allowed(self, name):
        if self.finished or self.submitted or self.used >= fixture.CALL_LIMIT:
            return False
        if name not in {tool["function"]["name"] for tool in self.tools}:
            return False
        if self.scoring == "mean":
            if fixture.CALL_LIMIT - self.used <= self.submission_limit - len(self.scores):
                return name == "submit"
        elif self.used >= 19:
            return name == "submit"
        elif self.used >= 18:
            return name in ("run_command", "submit")
        return True

    def publish(self, raw, feedback):
        try:
            submission = json.loads(raw)
        except (ValueError, TypeError, UnicodeError, RecursionError):
            submission = None
        number = len(self.scores)
        record = {"generation": self.spec["generation"], "seat": self.spec["seat"],
                  "submission_number": number, "submission": submission, "feedback": feedback}
        name = f"generation-{self.spec['generation']:02d}-seat-{self.spec['seat']}-submission-{number}.json"
        with (self.receipts / name).open("xb") as stream:
            stream.write(fixture.encode(record))
        self.public_receipts.append(name)

    def shutdown(self):
        if not self.stopped["verified"]:
            self.box.stop()
            self.stopped = {"verified": True, "at": now()}

    def step(self):
        self.check_execution()
        if self.finished:
            return
        if not self.pending:
            self.turns += 1
            available = [tool for tool in self.tools if self.allowed(tool["function"]["name"])]
            save(self.meta / "requests" / f"{self.turns:02d}.json",
                 {"messages": self.messages, "tools": available, "at": now()})
            if self.client is None:
                self.client = Client(self.config)
            self.check_execution()
            message, raw = self.client.complete(self.messages, tools=available)
            save(self.meta / "responses" / f"{self.turns:02d}.json", raw)
            self.check_execution()
            if truncated_response(raw):
                self.no_progress("Response truncated. Continue with a tool call.")
                return
            self.messages.append(assistant_message(message))
            self.pending.extend(message.get("tool_calls") or [])
        if not self.pending:
            self.no_progress("No tool call. Continue with a tool call.")
            return
        self.response_failures = 0
        call = self.pending.popleft()
        name = call.get("function", {}).get("name")
        if not self.allowed(name):
            self.phase_rejections += 1
            available_names = ", ".join(tool["function"]["name"] for tool in self.tools
                                        if self.allowed(tool["function"]["name"]))
            self.messages.append({"role": "tool", "tool_call_id": call["id"], "content":
                                  f"Finalization only. Available tools: {available_names}. Remaining calls: {20 - self.used}."})
            save(self.meta / "messages.json", self.messages)
            if self.phase_rejections >= 3:
                self.end_reason = "Finalization tool restriction rejected three times"
                self.finish()
            return
        self.phase_rejections = 0
        self.used += 1
        before = self.capture()[1]
        arguments = {}
        try:
            arguments = parse_args(call)
        except (ValueError, TypeError):
            name = "invalid"
        result = "Invalid tool or arguments."
        if (name == "run_command" and isinstance(arguments, dict) and set(arguments) == {"command"}
                and isinstance(arguments["command"], str) and len(arguments["command"]) <= 20000):
            self.check_execution()
            self.box.thaw()
            try:
                self.check_execution()
                code, output = self.box.exec("cd /workspace && " + arguments["command"], 30)
            finally:
                self.box.freeze()
            self.check_execution()
            result = f"exit_code={code}\n{output}"[:16000]
        elif name in ("test", "submit") and arguments == {}:
            self.check_execution()
            if name == "test" and self.tests >= 2:
                result = "Test limit reached."
            else:
                terminal = name == "submit" and len(self.scores) + 1 == self.submission_limit
                raw_submission, snapshot = self.capture()
                feedback = snapshot["feedback"]
                if name == "test":
                    self.tests += 1
                else:
                    self.scores.append(feedback.get("score", 0))
                    self.feedback = feedback
                    self.submitted = terminal
                event = {"tool": name, "call": self.used, "snapshot": snapshot,
                         "feedback_delivered_to_current_agent": not terminal,
                         "submission_number": len(self.scores) if name == "submit" else None}
                self.evaluations.append(event)
                save(self.meta / "evaluations" / f"{self.used:02d}.json", event)
                if terminal:
                    self.shutdown()
                if name == "submit":
                    self.publish(raw_submission, feedback)
                result = json.dumps(feedback)
        after = self.capture()[1]
        save(self.meta / "actions" / f"{self.used:02d}.json", {
            "call": self.used, "turn": self.turns, "tool": name, "arguments": arguments,
            "before": before, "after": after, "result": result, "at": now()})
        if not self.submitted:
            remaining = f"\nremaining_calls={fixture.CALL_LIMIT - self.used}"
            if self.scoring == "mean":
                remaining += f"\nremaining_submissions={self.submission_limit - len(self.scores)}"
                if not self.allowed("run_command"):
                    remaining += "\nOnly submit is available."
            elif self.used in (18, 19):
                remaining += ("\nFinalization: one run_command followed by submit, or submit now."
                              if self.used == 18 else "\nFinalization: submit only.")
            self.messages.append({"role": "tool", "tool_call_id": call["id"], "content": result + remaining})
        save(self.meta / "messages.json", self.messages)
        if self.submitted or self.used >= fixture.CALL_LIMIT:
            self.finish()

    def no_progress(self, reason):
        self.response_failures += 1
        self.messages.append({"role": "user", "content":
                              reason + f" Remaining calls: {fixture.CALL_LIMIT - self.used}."})
        save(self.meta / "messages.json", self.messages)
        if self.response_failures >= 3:
            self.error = "Three consecutive truncated or tool-free responses"
            self.finish()

    def finish(self):
        if self.finished:
            return
        try:
            self.shutdown()
        except Exception as error:
            self.error = self.error or repr(error)
        normal = self.error is None and self.stopped["verified"]
        score = sum(self.scores) / self.submission_limit
        save(self.meta / "shutdown.json", self.stopped)
        save(self.meta / "messages.json", self.messages)
        save(self.meta / "submission-snapshots.json", self.snapshots)
        save(self.directory / "end.json", {
            **self.spec, "started_at": self.started_at, "ended_at": now(), "normal": normal,
            "error": self.error, "status": "technical_failure" if not normal else
            "submitted" if self.submitted else "partial" if self.scores else "no_submit",
            "earned_score": score if normal else None, "evaluated_score": score,
            "submission_scores": self.scores, "submissions_used": len(self.scores),
            "submitted": self.submitted, "final_feedback": self.feedback,
            "public_receipts": self.public_receipts, "end_reason": self.end_reason,
            "used_calls": self.used, "tests_used": self.tests, "model_turns": self.turns,
            "best_observed_full_candidate_score": max((record["feedback"].get("score", 0)
                for record in self.snapshots if record.get("length") == 100), default=None),
            "evaluations": self.evaluations, "shutdown_verified": self.stopped["verified"]})
        self.finished = True


def run_generation(directory, spec, config, target, image, wiki, order_seed, agents, deadline, claim, guard=None):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=False)
    meta = directory / "meta"
    actors = []
    error = None
    sequence = 0
    receipts = wiki.parent / "submissions"
    receipts.mkdir(exist_ok=True)
    try:
        save(meta / "incoming.json", wiki_state(wiki, meta))
        save(meta / "incoming-submissions.json", wiki_state(receipts, meta))
        for seat in range(agents):
            require_time(deadline)
            actor_spec = {**spec, "seat": seat, "actor": f"{spec['chain']}-{spec['generation']:02d}-{seat}"}
            claim(actor_spec)
            actor = Actor(directory / f"seat-{seat}", actor_spec, config, target, image, wiki, deadline, guard)
            actors.append(actor)
            try:
                actor.start()
            except Exception as caught:
                actor.error = repr(caught)
                actor.finish()
                if not actor.stopped["verified"]:
                    raise RuntimeError("Generation stopped after unverified shutdown") from caught
        generator = random.Random(order_seed)
        round_number = 0
        while any(not actor.finished for actor in actors):
            round_number += 1
            active = [actor for actor in actors if not actor.finished]
            generator.shuffle(active)
            save(meta / "rounds" / f"{round_number:02d}.json", {"seats": [actor.spec["seat"] for actor in active]})
            for actor in active:
                sequence += 1
                before = wiki_state(wiki, meta)
                try:
                    actor.step()
                except Exception as caught:
                    actor.error = repr(caught)
                    actor.finish()
                if actor.finished and not actor.stopped["verified"]:
                    raise RuntimeError("Generation stopped after unverified shutdown")
                save(meta / "wiki-events" / f"{sequence:03d}.json", {
                    "round": round_number, "seat": actor.spec["seat"], "call": actor.used,
                    "before": before, "after": wiki_state(wiki, meta), "at": now()})
    except Exception as caught:
        error = repr(caught)
    finally:
        for actor in actors:
            if not actor.finished:
                actor.error = actor.error or error or "Generation interrupted"
                try:
                    actor.finish()
                except Exception as caught:
                    error = error or repr(caught)
        outgoing = None
        try:
            if any(not actor.stopped["verified"] for actor in actors):
                raise RuntimeError("Cannot archive an unverified generation shutdown")
            outgoing = wiki_state(wiki, meta)
            save(meta / "outgoing.json", outgoing)
            save(meta / "outgoing-submissions.json", wiki_state(receipts, meta))
        except Exception as caught:
            error = error or repr(caught)
        normal = error is None and len(actors) == agents and all(
            actor.error is None and actor.stopped["verified"] for actor in actors)
        result = {**spec, "normal": normal, "error": error, "outgoing": outgoing,
                  "ended_at": now(), "session_count": len(actors)}
        save(directory / "end.json", result)
    return result
