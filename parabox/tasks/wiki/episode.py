"""Bounded sandbox runtime for shared-workspace wiki tasks."""
from __future__ import annotations

import json
import os
from pathlib import Path, PurePosixPath
import tempfile
import threading

from parabox.model import Client, assistant_message, parse_args
from parabox.sandbox import Limits
from parabox.util import digest_json, now, read, save, sha256
from parabox.workspace import snapshot_regular, write_regular
from . import fixture
from .runtime.helpers import FastBox
from .runtime.helpers import before_deadline, fingerprints
from .runtime.prompts import assignment
from .runtime.service import Budget, ObjectService, ServiceServer
from .runtime.helpers import archive, shutdown, snapshot_solution


SYSTEM = "Call exactly one tool each turn."
TURNS = 40
BUDGET = 60
TOOLS = [
    {"type": "function", "function": {
        "name": "run_command", "description": "Run a shell command in /workspace.",
        "parameters": {"type": "object", "properties": {"command": {"type": "string"}},
                       "required": ["command"], "additionalProperties": False}}},
    {"type": "function", "function": {
        "name": "submit", "description": "Submit the scored files and end this session.",
        "parameters": {"type": "object", "properties": {}, "additionalProperties": False}}},
]


def service_objects() -> dict:
    return {f"{scope}/{package}/{index}": case
            for package in fixture.packages()
            for scope, cases in (("public", fixture.public_cases(package)),
                                 ("private", fixture.cases(package)))
            for index, case in enumerate(cases)}


def validate_files(files: dict[str, bytes], incoming: dict[str, bytes]) -> None:
    if set(files) & set(incoming):
        raise ValueError("Incoming file shadows fixture")
    total = 0
    for name, raw in {**files, **incoming}.items():
        path = PurePosixPath(name)
        if (not name or path.is_absolute() or ".." in path.parts or "\x00" in name
                or str(path) != name or not isinstance(raw, bytes)):
            raise ValueError("Invalid workspace file")
        if name in incoming and (len(path.parts) < 3 or path.parts[:2] not in
                                 (("shared", "wiki"), ("shared", "incoming"))):
            raise ValueError("Incoming files must be in shared/wiki or shared/incoming")
        total += len(raw)
        if len(raw) > 4 * 1024 * 1024 or total > 16 * 1024 * 1024:
            raise ValueError("Workspace input exceeds size limit")
    if len(files) + len(incoming) > 4096:
        raise ValueError("Workspace input exceeds entry limit")
    if "solution.py" not in files:
        raise ValueError("Missing solution.py")


def wiki_snapshot(workspace: Path, meta: Path) -> dict:
    descriptor = os.open(workspace, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for component in ("shared", "wiki"):
            child = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                            dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        files = snapshot_regular(f"/proc/self/fd/{descriptor}/.")
    except FileNotFoundError:
        files = {}
    finally:
        os.close(descriptor)
    for raw in files.values():
        archive(meta, raw)
    return {"files": fingerprints(files)}


def snapshot(workspace: Path, meta: Path) -> dict:
    solution = snapshot_solution(workspace, meta)
    try:
        shared = wiki_snapshot(workspace, meta)
    except (OSError, ValueError) as caught:
        shared = {"files": {}, "error": str(caught)}
    return {"solution": solution, "wiki": shared}


def run_episode(directory: Path, spec: dict, config: dict, image: str, *,
                files: dict[str, bytes], incoming: dict[str, bytes], deadline: str) -> dict:
    return _run_episode(directory, spec, config, image, files=files, incoming=incoming,
                        deadline=deadline, budget_limit=BUDGET, client_factory=Client)


def _run_episode(directory: Path, spec: dict, config: dict, image: str, *,
                files: dict[str, bytes], incoming: dict[str, bytes], deadline: str,
                 budget_limit: int, client_factory) -> dict:
    if directory.exists():
        if (directory / "end.json").exists():
            return read(directory / "end.json")
        raise RuntimeError("Interrupted participant start is retained, not restarted")
    if not before_deadline(deadline):
        raise RuntimeError("Execution deadline reached")
    validate_files(files, incoming)
    if spec["package"] not in fixture.packages():
        raise ValueError("Unknown package")
    directory.mkdir(parents=True)
    workspace, meta = directory / "workspace", directory / "meta"
    workspace.mkdir()
    for name, raw in {**files, **incoming}.items():
        write_regular(workspace, name, raw)
    for relative in ("shared/wiki", "shared/incoming"):
        (workspace / relative).mkdir(parents=True, exist_ok=True)
    messages = [{"role": "system", "content": SYSTEM},
                {"role": "user", "content": assignment(spec["package"], spec.get("source", False))}]
    safe_config = {key: config[key] for key in ("model", "wire", "temperature", "max_tokens")
                   if key in config}
    save(meta / "spec.json", spec)
    save(meta / "config.json", {"config": safe_config, "image": image,
                               "budget": budget_limit, "turns": TURNS, "deadline": deadline})
    save(meta / "incoming.json", {"files": fingerprints(incoming)})
    save(meta / "workspace.json", fingerprints(files))
    save(meta / "prompts.json", {"messages": messages, "tools": TOOLS})
    initial = snapshot(workspace, meta)
    save(meta / "initial.json", initial)
    save(meta / "initial-solution.json", initial["solution"])
    budget = Budget(budget_limit, meta / "budget.jsonl")
    started_at = now()
    box = server = worker = socket_directory = service = None
    stopped = {"verified": False}
    action = error = None
    turn = requests = 0
    deadline_reached = False
    service_closed = False
    runtime_events = []
    final = {}
    try:
        socket_directory = tempfile.TemporaryDirectory(prefix="session-")
        socket_root = Path(socket_directory.name)
        socket_root.chmod(0o755)
        service = ObjectService(service_objects(), budget, meta / "service.jsonl")
        server = ServiceServer(socket_root / "examples.sock", service)
        server.daemon_threads = False
        server.block_on_close = True
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        box = FastBox("session-" + sha256(str(directory.resolve()))[:16], workspace, image,
                      Limits(cpus="2", memory="2g"),
                      mounts=((str(socket_root), "/service", "ro"),
                              (str(workspace / "shared/incoming"),
                               "/workspace/shared/incoming", "ro")))
        box.start()
        client = client_factory(config)
        for turn in range(1, TURNS + 1):
            if not before_deadline(deadline):
                deadline_reached = True
                break
            if not budget.remaining:
                break
            save(meta / "requests" / f"t{turn:02d}.json", {"messages": messages, "sent_at": now()})
            requests += 1
            message, raw = client.complete(messages, tools=TOOLS)
            save(meta / "responses" / f"t{turn:02d}.json", raw)
            messages.append(assistant_message(message))
            if not before_deadline(deadline):
                deadline_reached = True
                break
            calls = message.get("tool_calls") or []
            if not isinstance(calls, list):
                calls = []
            for index, call in enumerate(calls or [None]):
                before = snapshot(workspace, meta)
                function = call.get("function", {}) if isinstance(call, dict) else {}
                name = function.get("name") if isinstance(function, dict) else None
                charge = budget.charge(name if name in ("run_command", "submit") else "invalid_action",
                                       {"turn": turn, "index": index})
                arguments = {}
                result = "Invalid tool or arguments."
                if not charge["accepted"]:
                    result = "Execution budget exhausted."
                elif len(calls) != 1 or not isinstance(call, dict):
                    result = "Call exactly one tool each turn."
                else:
                    try:
                        encoded = function.get("arguments")
                        if not isinstance(encoded, (dict, str)) or encoded == "":
                            raise ValueError("Expected an argument object")
                        if isinstance(encoded, str) and not isinstance(json.loads(encoded), dict):
                            raise ValueError("Expected an argument object")
                        arguments = parse_args(call)
                        if name == "submit" and arguments == {}:
                            service.seal()
                            action = "submit"
                            stopped = shutdown(box)
                            if not stopped["verified"]:
                                raise RuntimeError("Participant shutdown was not verified")
                            result = "Session ended."
                        elif (name == "run_command" and set(arguments) == {"command"}
                              and isinstance(arguments["command"], str)
                              and len(arguments["command"]) <= 20000):
                            code, output = box.exec("cd /workspace && " + arguments["command"], 30)
                            result = f"exit_code={code}\n{output}"[:16000]
                            if code != 0 and output.startswith("Error:") and any(
                                    marker in output for marker in ("OCI", "crun:", "container", "cgroup.procs")):
                                runtime_events.append({"turn": turn, "exit_code": code, "output": output[-2000:]})
                        else:
                            result = "Invalid tool or arguments."
                    except (ValueError, TypeError, AttributeError):
                        result = "Invalid tool or arguments."
                    except Exception as caught:
                        error = type(caught).__name__
                        result = "Execution failed."
                result += f"\nremaining_budget={budget.remaining}"
                after = snapshot(workspace, meta)
                save(meta / "actions" / f"t{turn:02d}-{index:02d}.json", {
                    "turn": turn, "index": index, "tool": name, "arguments": arguments,
                    "charge": charge, "result": result, "before": before, "after": after,
                    "recorded_at": now()})
                if isinstance(call, dict):
                    messages.append({"role": "tool", "tool_call_id": call.get("id") or f"call-{turn}-{index}",
                                     "content": result})
                else:
                    messages.append({"role": "user", "content": result})
                if action and stopped["verified"]:
                    save(meta / "submission-intent.json", {
                        "turn": turn, "recorded_at": now(), "solution": after["solution"]})
                    break
            if action or runtime_events or error:
                break
    except Exception as caught:
        error = type(caught).__name__
    finally:
        if service is not None:
            service.seal()
        if box is not None and not stopped["verified"]:
            try:
                stopped = shutdown(box)
            except Exception as caught:
                stopped = {"verified": False, "error": type(caught).__name__, "checked_at": now()}
        try:
            if server is not None:
                if worker is not None and worker.is_alive():
                    server.shutdown()
                server.server_close()
            if worker is not None:
                worker.join(timeout=5)
                if worker.is_alive():
                    raise RuntimeError("Service thread did not stop")
            if socket_directory is not None:
                socket_directory.cleanup()
            service_closed = True
        except Exception as caught:
            error = type(caught).__name__
    if stopped["verified"]:
        final = snapshot(workspace, meta)
    normal = not error and not deadline_reached and not runtime_events and stopped["verified"] and service_closed
    save(meta / "shutdown.json", stopped)
    save(meta / "messages.json", messages)
    save(meta / "outgoing.json", final.get("wiki", {"files": {}}))
    save(meta / "final-solution.json", final.get("solution", {}))
    end = {**spec, "normal": normal, "action": action, "error": error,
           "status": "technical_failure" if not normal else "submitted" if action else "no_submission",
           "awarded_score": None if normal and action == "submit" else 0 if normal else None,
           "deadline_reached": deadline_reached, "shutdown_verified": stopped["verified"],
           "service_closed": service_closed, "runtime_events": runtime_events,
           "turn": turn, "requests": requests, "budget_used": budget.used,
           "remaining_budget": budget.remaining, "started_at": started_at, "ended_at": now(),
           "initial_solution": initial["solution"],
           "final_solution": final.get("solution", {}), "outgoing": final.get("wiki", {}),
           "shared": {"wiki": final.get("wiki", {})},
           "bindings": {"files": digest_json(fingerprints(files)),
                        "incoming": digest_json(fingerprints(incoming)),
                        "prompts": sha256((meta / "prompts.json").read_bytes()),
                        "config": sha256((meta / "config.json").read_bytes()),
                        "configuration_digest": digest_json(config),
                        "runtime": sha256(Path(__file__).read_bytes())}}
    save(directory / "end.json", end)
    return end
