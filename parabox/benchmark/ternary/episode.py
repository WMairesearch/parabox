"""Terminal or repeated submissions on a persistent wiki, with one or four agents."""
from collections import deque
import json
from pathlib import Path
import random
import subprocess
import copy

from parabox.workspace import snapshot_regular
from . import fixture
from .runtime import base


ASSIGNMENT = fixture.ASSIGNMENT
SUBMISSION_LIMIT = 3
TOOLS = copy.deepcopy(fixture.TOOLS)
TERMINAL_TOOLS = copy.deepcopy(fixture.TERMINAL_TOOLS)


def participant_files(prefix, target, protocol=fixture.REPEATED):
    if protocol == fixture.TERMINAL:
        return fixture.terminal_workspace_files(prefix, target)
    if protocol == fixture.REPEATED:
        return fixture.workspace_files(prefix, target)
    raise ValueError("Unknown ternary protocol")


def truncated_response(value):
    if isinstance(value, dict):
        return any((key in ("finish_reason", "finishReason") and item in ("length", "MAX_TOKENS"))
                   or (key == "stop_reason" and item == "max_tokens")
                   or (key == "incomplete_details" and isinstance(item, dict)
                       and item.get("reason") == "max_output_tokens")
                   or (isinstance(item, (dict, list)) and truncated_response(item))
                   for key, item in value.items())
    if isinstance(value, list):
        return any(truncated_response(item) for item in value)
    return False


class SharedBox(base.Box):
    def exec(self, command, timeout, env=None):
        argv = ["podman", "exec"]
        for key, value in (env or {}).items():
            argv += ["-e", f"{key}={value}"]
        argv += [self.name, "bash", "-lc", command]
        try:
            result = subprocess.run(argv, capture_output=True, timeout=timeout)
            return result.returncode, (result.stdout + result.stderr).decode("utf-8", errors="replace")
        except subprocess.TimeoutExpired as error:
            output = b"".join(part or b"" for part in (error.stdout, error.stderr))
            return 124, output.decode("utf-8", errors="replace") + "\nTIMEOUT"

    def freeze(self):
        subprocess.run(["podman", "pause", self.name], check=True,
                       capture_output=True, timeout=15)

    def thaw(self):
        subprocess.run(["podman", "unpause", self.name], check=True,
                       capture_output=True, timeout=15)


def wiki_state(wiki, meta):
    return {name: base.archive(meta, raw) for name, raw in snapshot_regular(wiki).items()}


class Actor:
    def __init__(self, directory, spec, config, target, image, wiki, deadline,
                 protocol=fixture.REPEATED):
        self.directory, self.spec, self.target = directory, spec, target
        self.protocol = protocol
        self.tools = TERMINAL_TOOLS if protocol == fixture.TERMINAL else TOOLS
        self.workspace, self.meta = directory / "workspace", directory / "meta"
        directory.mkdir(parents=True, exist_ok=False)
        self.workspace.mkdir()
        files = participant_files(spec["prefix"], target, protocol)
        for name, raw in files.items():
            base.write_regular(self.workspace, name, raw)
        (self.workspace / "shared/wiki").mkdir(parents=True)
        (self.workspace / "shared/submissions").mkdir(parents=True)
        self.receipts = wiki.parent / "submissions"
        self.receipts.mkdir(exist_ok=True)
        self.messages = [{"role": "system", "content": fixture.SYSTEM},
                         {"role": "user", "content": fixture.TERMINAL_ASSIGNMENT
                          if protocol == fixture.TERMINAL else ASSIGNMENT}]
        base.save(self.meta / "prompts.json", {
            "messages": self.messages, "tools": self.tools,
            "files": {name: raw.decode() for name, raw in files.items()}})
        base.save(self.meta / "spec.json", spec)
        box_prefix = "ternary-terminal-" if protocol == fixture.TERMINAL else "ternary-repeated-"
        self.box = SharedBox(box_prefix + base.sha256(str(directory.resolve()))[:16],
            self.workspace, image, base.Limits(cpus="2", memory="2g"),
            mounts=((str(wiki), "/workspace/shared/wiki", "rw,z"),
                    (str(self.receipts), "/workspace/shared/submissions", "ro,z")))
        from parabox.execution.control.guards import DeadlineClient
        self.client = DeadlineClient(base.Client(config), deadline)
        self.pending = deque()
        self.used = self.turns = self.tests = 0
        self.scores = []
        self.public_receipts = []
        self.submitted = False
        self.error = None
        self.finished = False
        self.stopped = {"verified": False}
        self.feedback = None
        self.public_receipt = None
        self.response_failures = self.phase_rejections = 0
        self.end_reason = None
        self.public_receipt = None
        self.evaluations, self.snapshots = [], []
        self.started_at = base.now()
        self.capture()

    def capture(self):
        record = base.capture(self.workspace, self.meta, self.target)[1]
        self.snapshots.append(record)
        return record

    def start(self):
        try:
            self.box.start()
            self.box.freeze()
        except Exception as error:
            self.error = repr(error)
            self.finish()

    def step(self):
        if not self.pending:
            self.turns += 1
            available = [tool for tool in self.tools if self.allowed(tool["function"]["name"])]
            base.save(self.meta / "requests" / f"{self.turns:02d}.json",
                      {"messages": self.messages, "tools": available, "at": base.now()})
            message, raw = self.client.complete(self.messages, tools=available)
            base.save(self.meta / "responses" / f"{self.turns:02d}.json", raw)
            if truncated_response(raw):
                self.no_progress("Response truncated. Continue with a tool call.")
                return
            self.messages.append(base.assistant_message(message))
            self.pending.extend(message.get("tool_calls") or [])
        if not self.pending:
            self.no_progress("No tool call. Continue with a tool call.")
            return
        self.response_failures = 0
        call = self.pending.popleft()
        name = call.get("function", {}).get("name")
        if not self.allowed(name):
            self.phase_rejections += 1
            self.messages.append({"role": "tool", "tool_call_id": call["id"], "content":
                f"Finalization only. Available tools: {', '.join(tool['function']['name'] for tool in self.tools if self.allowed(tool['function']['name']))}. Remaining calls: {20 - self.used}."})
            base.save(self.meta / "messages.json", self.messages)
            if self.phase_rejections >= 3:
                self.end_reason = "Finalization tool restriction rejected three times"
                self.finish()
            return
        self.phase_rejections = 0
        self.used += 1
        before = self.capture()
        arguments = {}
        try:
            arguments = base.parse_args(call)
        except (ValueError, TypeError):
            name = "invalid"
        result = "Invalid tool or arguments."
        if (name == "run_command" and isinstance(arguments, dict) and set(arguments) == {"command"}
                and isinstance(arguments["command"], str) and len(arguments["command"]) <= 20000):
            self.box.thaw()
            try:
                code, output = self.box.exec("cd /workspace && " + arguments["command"], 30)
            finally:
                self.box.freeze()
            result = f"exit_code={code}\n{output}"[:16000]
        elif self.protocol == fixture.TERMINAL and name in ("test", "submit") and arguments == {}:
            if name == "test" and self.tests >= 2:
                result = "Test limit reached."
            else:
                if name == "submit":
                    self.stopped = base.shutdown(self.box)
                    if not self.stopped["verified"]:
                        raise RuntimeError("Unverified shutdown")
                    self.submitted = True
                else:
                    self.tests += 1
                snapshot = self.capture()
                feedback = snapshot["feedback"]
                event = {"tool": name, "call": self.used, "snapshot": snapshot,
                         "feedback_delivered_to_current_agent": name == "test"}
                self.evaluations.append(event)
                base.save(self.meta / "evaluations" / f"{self.used:02d}.json", event)
                if self.submitted:
                    self.feedback = feedback
                    raw_submission = base.capture(self.workspace, self.meta, self.target)[0]
                    try:
                        submission = json.loads(raw_submission)
                    except (ValueError, UnicodeError, RecursionError):
                        submission = None
                    record = {"generation": self.spec["generation"], "seat": self.spec["seat"],
                              "submission": submission, "feedback": feedback}
                    name_on_disk = f"generation-{self.spec['generation']:02d}-seat-{self.spec['seat']}.json"
                    with (self.receipts / name_on_disk).open("xb") as stream:
                        stream.write(fixture.encode(record))
                    self.public_receipt = name_on_disk
                result = json.dumps(feedback)
        elif self.protocol == fixture.REPEATED and name == "submit" and arguments == {}:
            snapshot = self.capture()
            feedback = snapshot["feedback"]
            self.scores.append(feedback.get("score", 0))
            self.feedback = feedback
            self.submitted = len(self.scores) == SUBMISSION_LIMIT
            event = {"tool": name, "call": self.used, "submission_number": len(self.scores),
                     "snapshot": snapshot,
                     "feedback_delivered_to_current_agent": not self.submitted}
            self.evaluations.append(event)
            base.save(self.meta / "evaluations" / f"{self.used:02d}.json", event)
            if self.submitted:
                self.stopped = base.shutdown(self.box)
                if not self.stopped["verified"]:
                    raise RuntimeError("Unverified shutdown")
            raw_submission = base.capture(self.workspace, self.meta, self.target)[0]
            try:
                submission = json.loads(raw_submission)
            except (ValueError, TypeError, UnicodeError, RecursionError):
                submission = None
            record = {"generation": self.spec["generation"], "seat": self.spec["seat"],
                      "submission_number": len(self.scores),
                      "submission": submission, "feedback": feedback}
            name_on_disk = (f"generation-{self.spec['generation']:02d}-seat-{self.spec['seat']}"
                            f"-submission-{len(self.scores)}.json")
            with (self.receipts / name_on_disk).open("xb") as stream:
                stream.write(fixture.encode(record))
            self.public_receipts.append(name_on_disk)
            result = json.dumps(feedback)
        after = self.capture()
        base.save(self.meta / "actions" / f"{self.used:02d}.json", {
            "call": self.used, "turn": self.turns, "tool": name, "arguments": arguments,
            "before": before, "after": after, "result": result, "at": base.now()})
        if not self.submitted:
            content = result + f"\nremaining_calls={base.CALL_LIMIT - self.used}"
            if self.protocol == fixture.TERMINAL:
                content += ("\nFinalization: one run_command followed by submit, or submit now."
                            if self.used == 18 else "\nFinalization: submit only."
                            if self.used == 19 else "")
            else:
                content += (f"\nremaining_submissions={SUBMISSION_LIMIT - len(self.scores)}" +
                            ("\nOnly submit is available." if not self.allowed("run_command") else ""))
            self.messages.append({"role": "tool", "tool_call_id": call["id"], "content": content})
        base.save(self.meta / "messages.json", self.messages)
        if self.submitted or self.used >= base.CALL_LIMIT:
            self.finish()

    def allowed(self, name):
        if self.protocol == fixture.TERMINAL:
            if self.used >= 19:
                return name == "submit"
            if self.used >= 18:
                return name in ("run_command", "submit")
            return True
        if name not in ("run_command", "submit") or self.finished:
            return False
        remaining = SUBMISSION_LIMIT - len(self.scores)
        if base.CALL_LIMIT - self.used <= remaining:
            return name == "submit"
        return True

    def no_progress(self, reason):
        self.response_failures += 1
        self.messages.append({"role": "user", "content":
            reason + f" Remaining calls: {base.CALL_LIMIT - self.used}."})
        base.save(self.meta / "messages.json", self.messages)
        if self.response_failures >= 3:
            self.error = "Three consecutive truncated or tool-free responses"
            self.finish()

    def finish(self):
        if self.finished:
            return
        if not self.stopped["verified"]:
            try:
                self.stopped = base.shutdown(self.box)
            except Exception as error:
                self.error = self.error or repr(error)
        normal = self.error is None and self.stopped["verified"]
        if self.protocol == fixture.TERMINAL:
            score = (self.feedback.get("score", 0) if self.submitted else 0) if normal else None
            evaluated = self.feedback.get("score", 0) if self.submitted and self.feedback is not None else None
            status = "technical_failure" if not normal else "submitted" if self.submitted else "no_submit"
        else:
            score = sum(self.scores) / SUBMISSION_LIMIT if normal else None
            evaluated = sum(self.scores) / SUBMISSION_LIMIT
            status = "technical_failure" if not normal else "submitted" if self.submitted else "partial" if self.scores else "no_submit"
        base.save(self.meta / "shutdown.json", self.stopped)
        base.save(self.meta / "messages.json", self.messages)
        base.save(self.meta / "submission-snapshots.json", self.snapshots)
        end = {
            **self.spec, "started_at": self.started_at, "ended_at": base.now(),
            "normal": normal, "error": self.error,
            "status": status,
            "earned_score": score, "final_feedback": self.feedback, "submitted": self.submitted,
            "evaluated_score": evaluated,
            "end_reason": self.end_reason,
            "used_calls": self.used, "model_turns": self.turns,
            "best_observed_full_candidate_score": max((record["feedback"].get("score", 0)
                for record in self.snapshots if record.get("length") == 100), default=None),
            "evaluations": self.evaluations}
        if self.protocol == fixture.TERMINAL:
            end.update(public_receipt=self.public_receipt, tests_used=self.tests)
        else:
            end.update(public_receipts=self.public_receipts, submission_scores=self.scores,
                       submissions_used=len(self.scores))
        base.save(self.directory / "end.json", end)
        self.finished = True


def run_generation(directory: Path, spec, config, target, image, wiki, order_seed, deadline,
                   agents=4, protocol=fixture.REPEATED):
    directory.mkdir(parents=True, exist_ok=False)
    meta = directory / "meta"
    actors = []
    error = None
    sequence = 0
    base.save(meta / "incoming.json", wiki_state(wiki, meta))
    receipts = wiki.parent / "submissions"
    receipts.mkdir(exist_ok=True)
    base.save(meta / "incoming-submissions.json", wiki_state(receipts, meta))
    try:
        for seat in range(agents):
            actor = Actor(directory / f"seat-{seat}", {**spec, "seat": seat},
                          config, target, image, wiki, deadline, protocol)
            actors.append(actor)
            actor.start()
        generator = random.Random(order_seed)
        round_number = 0
        while any(not actor.finished for actor in actors):
            round_number += 1
            active = [actor for actor in actors if not actor.finished]
            generator.shuffle(active)
            base.save(meta / "rounds" / f"{round_number:02d}.json",
                      {"seats": [actor.spec["seat"] for actor in active]})
            for actor in active:
                sequence += 1
                before = wiki_state(wiki, meta)
                try:
                    actor.step()
                except Exception as caught:
                    actor.error = repr(caught)
                    actor.finish()
                after = wiki_state(wiki, meta)
                base.save(meta / "wiki-events" / f"{sequence:03d}.json", {
                    "round": round_number, "seat": actor.spec["seat"], "call": actor.used,
                    "before": before, "after": after, "at": base.now()})
    except Exception as caught:
        error = repr(caught)
    finally:
        for actor in actors:
            if not actor.finished:
                actor.error = actor.error or error or "Generation interrupted"
                actor.finish()
        outgoing = None
        try:
            outgoing = wiki_state(wiki, meta)
            base.save(meta / "outgoing.json", outgoing)
            base.save(meta / "outgoing-submissions.json", wiki_state(receipts, meta))
        except Exception as caught:
            error = error or repr(caught)
        normal = (error is None and len(actors) == agents
                  and all(actor.finished and actor.stopped.get("verified") is True
                          and actor.error is None for actor in actors))
        result = {**spec, "normal": normal, "error": error, "outgoing": outgoing,
                  "ended_at": base.now(), "session_count": len(actors)}
        base.save(directory / "end.json", result)
    return result
