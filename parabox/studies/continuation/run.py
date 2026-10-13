"""Select, prepare, continue, audit, and report truncated Gemini sessions."""
from __future__ import annotations

import asyncio
import csv
import hashlib
import json
import shutil
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from parabox import model
from parabox.model import assistant_message, parse_args
from parabox.sandbox import Box, Limits, image_exists
from parabox.session import IGNORED, NO_TOOL
from parabox.studies.composition.task import CompositionTask
from parabox.studies.continuation import census as C
from parabox.studies.continuation import recover as R
from parabox.studies.relay.run import CONCURRENCY, code_commit, session_dir
from parabox.tasks.base import SessionState, run_audit_session
from parabox.tasks.code import audit as A
from parabox.tasks.code.mechspan import MechspanCodeTask
from parabox.util import ROOT, now, read, save, sha256

EXTRA_TURNS = 8
ERROR_BUDGET_S = 15 * 60
CSV_FIELDS = (
    "actor", "arm", "problem", "orig_turns", "orig_submits", "orig_accepted",
    "orig_conftest_unsubmitted", "recovery_case", "cont_turns", "cont_submits",
    "cont_accepted", "cont_violation", "cont_finished", "cont_conftest_present",
    "new_notes",
)
PHASE1_COUNTS = {
    "hygienic-chain-gemini": 29,
    "composition-gemini": 50,
    "hinted-a2-gemini": 22,
}
PHASE2_COUNTS = {
    "mechspan-code-gemini": 107,
}


def source_protocol(run_dir: Path) -> dict:
    return read(Path(run_dir) / "protocol.json")


def protocol_sha256(run_dir: Path) -> str:
    return sha256((Path(run_dir) / "protocol.json").read_bytes())


def make_task(protocol: dict, spec: dict | None = None):
    frozen = protocol.get("frozen") or {}
    study = protocol.get("study")
    task_name = frozen.get("task")
    verifier = protocol.get("verifier") or frozen.get("verifier")
    if task_name == "mechspan_code" or study == "mechspan_code":
        arm = (spec or {}).get("arm") or "A2"
        return MechspanCodeTask(arm)
    if task_name == "composition_code" or study == "composition" or verifier in ("hygienic", "hygienic-a2"):
        return CompositionTask()
    raise SystemExit(f"unknown source task {task_name!r} study={study!r}")


def is_mechspan(protocol: dict) -> bool:
    frozen = protocol.get("frozen") or {}
    return frozen.get("task") == "mechspan_code" or protocol.get("study") == "mechspan_code"


def integrity_of(protocol: dict) -> str:
    return (protocol.get("frozen") or {}).get("integrity") or "plain"


def limits_of(protocol: dict) -> Limits:
    container = (protocol.get("frozen") or {}).get("container") or {}
    return Limits(cpus=str(container.get("cpus") or "2"), memory=str(container.get("memory") or "2g"))


def image_of(protocol: dict) -> str:
    return (protocol.get("frozen") or {}).get("image") or "localhost/parabox-code:py312"


def model_config_of(protocol: dict) -> dict:
    cfg = dict((protocol.get("frozen") or {}).get("model") or {})
    cfg.pop("api_key", None)
    if not cfg:
        return model.load_config()
    return cfg


def load_plan(directory: Path) -> list[dict]:
    return read(directory / "plan.json")["actors"]


def status(directory: Path, **fields) -> None:
    save(directory / "status.json", {"updated_at": now(), **fields})


def merge_selected_csv(path: Path, rows: list[dict]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = []
    if path.exists():
        with path.open(newline="") as handle:
            existing = list(csv.DictReader(handle))
    keep = [row for row in existing if row.get("source_run") not in {r["source_run"] for r in rows}]
    fields = [
        "source_run", "source_path", "actor", "arm", "problem",
        "orig_turns", "orig_submits", "orig_accepted", "orig_conftest_unsubmitted", "limit",
    ]
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in keep + rows:
            writer.writerow({key: row.get(key, "") for key in fields})


def select(source_run: Path, out: Path) -> list[dict]:
    source_run = Path(source_run)
    rows = C.select_sessions(source_run)
    merge_selected_csv(out, rows)
    expected = PHASE1_COUNTS.get(source_run.name) or PHASE2_COUNTS.get(source_run.name)
    print(f"{source_run.name}: selected {len(rows)}" + (f" (expected {expected})" if expected else ""))
    if expected is not None and len(rows) != expected:
        print(
            f"SELECTION MISMATCH {source_run.name}: got {len(rows)}, census expected {expected}. "
            "Not forcing the count."
        )
    return rows


def _copy_session(src: Path, dest: Path) -> None:
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(src, dest, symlinks=True)


def _shared_files(workspace: Path) -> dict[str, str]:
    shared = workspace / "shared"
    out = {}
    if not shared.exists():
        return out
    for path in sorted(shared.rglob("*")):
        if not path.is_file():
            continue
        rel = "shared/" + str(path.relative_to(shared)).replace("\\", "/")
        out[rel] = sha256(path.read_bytes())
    return out


def _file_fingerprint(path: Path) -> str:
    return sha256(path.read_bytes()) if path.is_file() else ""


def _snapshot_originals(session: Path) -> dict:
    meta = session / "meta"
    files = {}
    for folder in ("requests", "responses", "submissions"):
        root = meta / folder
        if not root.is_dir():
            continue
        for path in sorted(root.iterdir()):
            if path.is_file():
                files[str(path.relative_to(meta))] = _file_fingerprint(path)
    if (meta / "submissions.json").exists():
        files["submissions.json"] = _file_fingerprint(meta / "submissions.json")
    return {
        "files": files,
        "shared": _shared_files(session / "workspace"),
        "submissions": read(meta / "submissions.json") if (meta / "submissions.json").exists() else [],
    }


def _peek_t16_call(session: Path) -> tuple[str | None, dict]:
    path = R.last_response_path(session)
    if path is None:
        return None, {}
    assistant = R.assistant_from_raw(read(path))
    calls = assistant.get("tool_calls") or []
    if not calls:
        return None, {}
    from parabox.model import parse_args
    name = (calls[0].get("function") or {}).get("name")
    try:
        args = parse_args(calls[0])
    except Exception:
        args = {}
    return name, args


def prepare_session(src: Path, dest: Path, protocol: dict, prefix: str) -> dict:
    _copy_session(src, dest)
    spec = read(dest / "meta" / "spec.json")
    task = make_task(protocol, spec)
    image = image_of(protocol)
    name, args = _peek_t16_call(dest)
    box = None
    if R.recovery_kind(name, args) == "reexecute":
        if not image_exists(image):
            raise SystemExit(f"image {image} is missing")
        box = Box(f"{prefix}-prep-{dest.name}"[:75], dest / "workspace", image, limits_of(protocol))
        box.start()
    try:
        messages, info = R.rebuild_messages(dest, task, box)
    finally:
        if box is not None:
            box.stop()
    snap = _snapshot_originals(dest)
    save(dest / "meta" / "continuation" / "start-messages.json", messages)
    save(dest / "meta" / "continuation" / "recovery.json", info)
    save(dest / "meta" / "continuation" / "original-snapshot.json", snap)
    if (dest / "end.json").exists():
        shutil.copy2(dest / "end.json", dest / "meta" / "continuation" / "end-source.json")
    return info


def prepare(source_run: Path, dest_run: Path) -> dict:
    source_run = Path(source_run).resolve()
    dest_run = Path(dest_run).resolve()
    if dest_run == source_run or source_run in dest_run.parents:
        raise SystemExit("dest must not be inside the source run")
    if dest_run.exists() and (dest_run / "cont-protocol.json").exists():
        raise SystemExit(f"{dest_run} is already prepared")
    protocol = source_protocol(source_run)
    rows = C.select_sessions(source_run)
    if not rows:
        raise SystemExit(f"no truncated-not-accepted sessions in {source_run}")
    dest_run.mkdir(parents=True, exist_ok=True)
    prefix = "pbk" + sha256(str(dest_run))[:6]
    recoveries = {}

    def one(row: dict) -> tuple[str, dict]:
        src = session_dir(source_run, row["actor"])
        dest = session_dir(dest_run, row["actor"])
        info = prepare_session(src, dest, protocol, prefix)
        print(row["actor"], info["recovery_case"], info.get("tool"), flush=True)
        return row["actor"], info

    with ThreadPoolExecutor(CONCURRENCY) as pool:
        for actor, info in pool.map(one, rows):
            recoveries[actor] = info

    actors = []
    for row in rows:
        info = recoveries[row["actor"]]
        actors.append({**row, "recovery_case": info["recovery_case"], "recovery_tool": info.get("tool")})
    save(dest_run / "plan.json", {"actors": actors})
    save(dest_run / "schedule.json", actors)
    save(dest_run / "cont-protocol.json", {
        "study": "continuation",
        "prepared_at": now(),
        "code_commit": code_commit(),
        "source_run": str(source_run),
        "source_run_name": source_run.name,
        "source_protocol_sha256": protocol_sha256(source_run),
        "extra_turns": EXTRA_TURNS,
        "extension_message": R.EXTENSION,
        "container_prefix": prefix,
        "source_study": protocol.get("study"),
        "source_verifier": protocol.get("verifier") or (protocol.get("frozen") or {}).get("verifier"),
        "source_protocol": {
            "study": protocol.get("study"),
            "verifier": protocol.get("verifier"),
            "arms": protocol.get("arms"),
            "frozen": protocol.get("frozen"),
        },
        "sessions": {actor: recoveries[actor] for actor in recoveries},
    })
    shutil.copy2(source_run / "protocol.json", dest_run / "source-protocol.json")
    status(dest_run, state="prepared", sessions=len(actors))
    print(f"prepared {dest_run} ({len(actors)} sessions)")
    return {"sessions": len(actors), "recovery": Counter(i["recovery_case"] for i in recoveries.values())}


def _load_state(target: Path) -> SessionState:
    spec = read(target / "meta" / "spec.json")
    submissions = read(target / "meta" / "submissions.json") if (target / "meta" / "submissions.json").exists() else []
    feedback = read(target / "meta" / "feedback.json") if (target / "meta" / "feedback.json").exists() else []
    report = None
    report_path = target / "meta" / "report.txt"
    if report_path.exists():
        report = report_path.read_text()
    return SessionState(
        problem=spec["problem"],
        workspace=target / "workspace",
        meta=target / "meta",
        shared=False,
        turn=0,
        submits=len(submissions),
        submissions=list(submissions),
        feedback=list(feedback),
        report=report,
        finished=False,
    )


def _append_tool_messages(messages: list[dict], message: dict, result: str, ignored: list[dict], turn: int) -> None:
    messages.append(assistant_message(message))
    calls = message.get("tool_calls") or []
    if not calls:
        messages.append({"role": "user", "content": NO_TOOL})
        return
    call = calls[0]
    messages.append({"role": "tool", "tool_call_id": call.get("id") or f"call-{turn}", "content": result})
    for extra in ignored:
        messages.append({
            "role": "tool",
            "tool_call_id": extra.get("id") or f"call-{turn}-ignored",
            "content": IGNORED,
        })


def _highest_turn(folder: Path) -> int:
    if not folder.is_dir():
        return 0
    turns = []
    for path in folder.glob("t*.json"):
        try:
            turns.append(int(path.stem[1:]))
        except ValueError:
            continue
    return max(turns) if turns else 0


def _replay_completed(target: Path, start_turn: int) -> list[dict] | None:
    """If continuation turns already have responses, resume from the last complete request."""
    requests = target / "meta" / "requests"
    responses = target / "meta" / "responses"
    last_resp = _highest_turn(responses)
    if last_resp < start_turn:
        return None
    last_req = _highest_turn(requests)
    if last_req >= last_resp and (requests / f"t{last_resp:02d}.json").exists():
        # Resume after a completed model call: take that request's messages plus
        # the already-saved assistant/tool if the next request exists; otherwise
        # stop before re-calling. The run loop starts at last_resp+1 only when
        # the tool result was persisted into the next request.
        nxt = requests / f"t{last_resp + 1:02d}.json"
        if nxt.exists():
            return list(read(nxt)["messages"])
    return None


def continue_session(task, client, box, target: Path, spec: dict, *, extra_turns: int = EXTRA_TURNS) -> dict:
    """Run +8 turns on a copied session. Never wipes workspace/meta or overwrites t01–t16."""
    meta = target / "meta"
    start_turn = 16 + 1
    end_turn = 16 + extra_turns
    cont = meta / "continuation"
    messages = read(cont / "start-messages.json")
    replayed = _replay_completed(target, start_turn)
    if replayed is not None:
        messages = replayed
        start_from = _highest_turn(meta / "requests")
        if (meta / "responses" / f"t{start_from:02d}.json").exists():
            start_from += 1
    else:
        start_from = start_turn
        # A leftover request without a response is safe to send (no model output yet).
        last_req = _highest_turn(meta / "requests")
        last_resp = _highest_turn(meta / "responses")
        if last_req >= start_turn and last_req > last_resp:
            messages = list(read(meta / "requests" / f"t{last_req:02d}.json")["messages"])
            start_from = last_req
    state = _load_state(target)
    orig_sub_n = len(state.submissions)
    tools = task.tools(shared=False)
    transcript = meta / "transcript.jsonl"
    normal, failure = False, None
    started = now()
    box.start()
    try:
        for turn in range(start_from, end_turn + 1):
            if state.finished:
                break
            state.turn = turn
            req_path = meta / "requests" / f"t{turn:02d}.json"
            resp_path = meta / "responses" / f"t{turn:02d}.json"
            if resp_path.exists():
                continue
            if not req_path.exists():
                save(req_path, {"turn": turn, "messages": messages, "sent_at": now()})
            else:
                messages = list(read(req_path)["messages"])
            message, raw = client.complete(messages, tools=tools)
            resp_path.parent.mkdir(exist_ok=True)
            resp_path.write_text(json.dumps(raw, ensure_ascii=False))
            calls = message.get("tool_calls") or []
            if not calls:
                result, ignored, name = NO_TOOL, [], None
                _append_tool_messages(messages, message, result, ignored, turn)
                _log(transcript, {"turn": turn, "tool": None})
                save(cont / "tools" / f"t{turn:02d}.json", {"name": None, "content": result})
                continue
            call, ignored = calls[0], calls[1:]
            name = (call.get("function") or {}).get("name")
            try:
                args = parse_args(call)
            except json.JSONDecodeError:
                result = "The tool arguments were not valid JSON."
            else:
                result = task.call(box, name, args, state)
            _append_tool_messages(messages, message, result, ignored, turn)
            save(cont / "tools" / f"t{turn:02d}.json", {
                "name": name, "content": result, "tool_call_id": call.get("id") or f"call-{turn}",
            })
            _log(transcript, {"turn": turn, "tool": name, "ignored": len(ignored)})
            if len(state.submissions) != orig_sub_n:
                save(meta / "submissions.json", state.submissions)
                orig_sub_n = len(state.submissions)
            if state.finished:
                break
        normal = True
    except Exception as exc:
        failure = repr(exc)
    finally:
        box.stop()
    save(meta / "submissions.json", state.submissions)
    save(meta / "feedback.json", state.feedback)
    if state.report is not None:
        (meta / "report.txt").write_text(state.report)
    cont_responses = [
        p for p in (meta / "responses").glob("t*.json")
        if _turn_num(p) >= 17
    ]
    end = {
        **{key: spec[key] for key in spec},
        "started_at": started, "ended_at": now(), "normal": normal, "error": failure,
        "turns": state.turn, "submits": state.submits, "finished": state.finished,
        "accepted": sum(bool(item.get("accepted")) for item in state.submissions),
        "feedback": len(state.feedback),
        "continuation": True,
        "cont_turns": len(cont_responses),
    }
    save(target / "end.json", end)
    save(cont / "end.json", end)
    return end


def _turn_num(path: Path) -> int:
    try:
        return int(path.stem[1:])
    except ValueError:
        return 0


def _log(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")


class NullBox:
    """Host-only box for the selftest. Tool calls that need exec are not used there."""

    def __init__(self, workspace: Path | None = None, *args, **kwargs):
        self.workspace = workspace

    def start(self) -> None:
        return None

    def stop(self) -> None:
        return None

    def exec(self, command, timeout, env=None):
        raise RuntimeError("NullBox cannot exec")


def run(directory: Path, *, client=None, concurrency: int = CONCURRENCY, sandbox: bool = True) -> list[dict]:
    directory = Path(directory)
    protocol = read(directory / "cont-protocol.json")
    source = protocol["source_protocol"]
    schedule = load_plan(directory)
    prefix = protocol["container_prefix"]
    extra = int(protocol.get("extra_turns") or EXTRA_TURNS)
    image = image_of(source)
    if client is None:
        if not image_exists(image):
            raise SystemExit(f"image {image} is missing")
        cfg = model_config_of(source)
        if "gemini-3.1-pro" not in str(cfg.get("model") or ""):
            raise SystemExit(f"source model is not Gemini 3.1 Pro: {cfg.get('model')}")
        client = model.Client(cfg)
    error_started: float | None = None
    stop_for_quota = False
    lock = asyncio.Lock()

    def one(row: dict) -> dict:
        nonlocal error_started, stop_for_quota
        if stop_for_quota:
            return {"actor": row["actor"], "normal": False, "error": "stopped: persistent API errors"}
        target = session_dir(directory, row["actor"])
        done = target / "meta" / "continuation" / "end.json"
        if done.exists() and read(done).get("normal"):
            return read(done)
        spec = read(target / "meta" / "spec.json")
        task = make_task(source, spec)
        if sandbox:
            box = Box(f"{prefix}-{row['actor']}"[:75], target / "workspace", image, limits_of(source))
        else:
            box = NullBox(target / "workspace")
        try:
            end = continue_session(task, client, box, target, spec, extra_turns=extra)
        except Exception as exc:
            end = {"actor": row["actor"], "normal": False, "error": repr(exc)}
            save(target / "meta" / "continuation" / "error.json", end)
        return end

    async def go_all(rows: list[dict]) -> list[dict]:
        nonlocal error_started, stop_for_quota
        sem = asyncio.Semaphore(concurrency)
        done: list[dict] = []

        async def go(row):
            nonlocal error_started, stop_for_quota
            async with sem:
                if stop_for_quota:
                    end = {"actor": row["actor"], "normal": False, "error": "stopped: persistent API errors"}
                    done.append(end)
                    return end
                try:
                    end = await asyncio.to_thread(one, row)
                except Exception as exc:
                    end = {"actor": row["actor"], "normal": False, "error": repr(exc)}
                async with lock:
                    if end.get("normal"):
                        error_started = None
                    elif end.get("error") and "stopped:" not in str(end.get("error")):
                        if error_started is None:
                            error_started = time.monotonic()
                        elif time.monotonic() - error_started > ERROR_BUDGET_S:
                            stop_for_quota = True
                            print("stopping: API errors persisted more than 15 minutes", flush=True)
                    done.append(end)
                    status(
                        directory, state="stopped" if stop_for_quota else "running",
                        finished=len(done), of=len(rows), last=row["actor"],
                        failed=[e["actor"] for e in done if not e.get("normal")],
                    )
                print(row["actor"], "normal" if end.get("normal") else end.get("error"), flush=True)
                return end

        return await asyncio.gather(*(go(row) for row in rows))

    status(directory, state="running", finished=0, of=len(schedule))
    ends = asyncio.run(go_all(schedule))
    failed = [end.get("actor") or "?" for end in ends if not end.get("normal")]
    if stop_for_quota:
        status(directory, state="stopped", failed=failed, reason="persistent API errors > 15 minutes")
    elif failed:
        status(directory, state="stopped", failed=failed)
    else:
        status(directory, state="complete")
    return ends


def _conftest_present(workspace: Path) -> bool:
    if not workspace.is_dir():
        return False
    return any(path.is_file() and path.name == "conftest.py" for path in workspace.rglob("conftest.py"))


def _new_notes(target: Path) -> list[str]:
    snap = {}
    path = target / "meta" / "continuation" / "original-snapshot.json"
    if path.exists():
        snap = read(path).get("shared") or {}
    now_files = _shared_files(target / "workspace")
    return sorted(name for name in now_files if name not in snap)


def _cont_violation(target: Path, protocol: dict) -> str:
    meta = target / "meta"
    session_audit = meta / "audit" / "session.json"
    if session_audit.exists():
        flag = read(session_audit).get("violation")
        if flag is None:
            return ""
        return "1" if flag else "0"
    flags = []
    for path in sorted((meta / "audit").glob("t*.json")) if (meta / "audit").is_dir() else []:
        item = read(path)
        if item.get("violation") is True:
            flags.append(True)
        elif item.get("violation") is False:
            flags.append(False)
    if not flags:
        return ""
    return "1" if any(flags) else "0"


def audit_session(directory: Path, target: Path) -> dict:
    protocol = read(directory / "cont-protocol.json")
    source = protocol["source_protocol"]
    spec = read(target / "meta" / "spec.json")
    task = make_task(source, spec)
    scratch = target / "meta" / "audit" / "scratch"
    if is_mechspan(source):
        results = []
        submissions = read(target / "meta" / "submissions.json") if (target / "meta" / "submissions.json").exists() else []
        for item in submissions:
            if not item.get("accepted"):
                continue
            out = target / "meta" / "audit" / f"t{item['turn']:02d}.json"
            raw = (target / "meta" / "submissions" / f"t{item['turn']:02d}.py").read_bytes()
            judged = A.audit_bytes(task.image, raw, spec["problem"], scratch / f"t{item['turn']:02d}", item.get("extras") or [])
            save(out, judged)
            results.append(judged)
        if not results:
            result = {"violation": None, "reason": "no_accepted"}
            save(target / "meta" / "audit" / "session.json", result)
            return result
        flags = [item.get("violation") for item in results]
        if any(flag is None for flag in flags):
            result = {"violation": None, "reason": "error", "turns": results}
        else:
            violation = any(flags)
            result = {"violation": violation, "reason": "gap" if violation else "clean", "turns": results}
        save(target / "meta" / "audit" / "session.json", result)
        return result
    result = run_audit_session(task, target, spec, scratch)
    save(target / "meta" / "audit" / "session.json", result)
    return result


def session_csv_row(directory: Path, row: dict) -> dict:
    protocol = read(directory / "cont-protocol.json")
    target = session_dir(directory, row["actor"])
    meta = target / "meta"
    submissions = read(meta / "submissions.json") if (meta / "submissions.json").exists() else []
    orig_n = int(row.get("orig_submits") or 0)
    snap = read(meta / "continuation" / "original-snapshot.json") if (meta / "continuation" / "original-snapshot.json").exists() else {}
    orig_subs = snap.get("submissions") if snap.get("submissions") is not None else submissions[:orig_n]
    new_subs = [item for item in submissions if int(item.get("turn") or 0) >= 17]
    cont_responses = [p for p in (meta / "responses").glob("t*.json") if _turn_num(p) >= 17]
    end = read(target / "end.json") if (target / "end.json").exists() else {}
    recovery = (protocol.get("sessions") or {}).get(row["actor"]) or {}
    if (meta / "continuation" / "recovery.json").exists():
        recovery = read(meta / "continuation" / "recovery.json")
    notes = _new_notes(target)
    return {
        "actor": row["actor"],
        "arm": row.get("arm") or "",
        "problem": row.get("problem") or "",
        "orig_turns": row.get("orig_turns") or "",
        "orig_submits": row.get("orig_submits") or 0,
        "orig_accepted": int(bool(row.get("orig_accepted"))),
        "orig_conftest_unsubmitted": int(bool(row.get("orig_conftest_unsubmitted"))),
        "recovery_case": recovery.get("recovery_case") or row.get("recovery_case") or "",
        "cont_turns": len(cont_responses),
        "cont_submits": len(new_subs),
        "cont_accepted": int(any(item.get("accepted") for item in submissions)),
        "cont_violation": _cont_violation(target, protocol),
        "cont_finished": int(bool(end.get("finished"))),
        "cont_conftest_present": int(_conftest_present(target / "workspace")),
        "new_notes": "|".join(notes),
        "_orig_subs": orig_subs,
        "_new_subs": new_subs,
    }


def write_csv(directory: Path, rows: list[dict]) -> Path:
    protocol = read(directory / "cont-protocol.json")
    name = protocol["source_run_name"]
    directory = Path(directory)
    local = directory / "results.csv"
    local.parent.mkdir(parents=True, exist_ok=True)
    with local.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in CSV_FIELDS})
    runs = (ROOT / "runs").resolve()
    try:
        directory.resolve().relative_to(runs)
    except ValueError:
        return local
    path = ROOT / "report" / "continuation" / f"{name}.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(local, path)
    return path


def audit(directory: Path) -> dict:
    directory = Path(directory)
    jobs = [session_dir(directory, row["actor"]) for row in load_plan(directory)]

    def one(target: Path) -> dict:
        result = audit_session(directory, target)
        print(target.name, result.get("reason"), flush=True)
        return result

    with ThreadPoolExecutor(CONCURRENCY) as pool:
        results = list(pool.map(one, jobs))
    rows = [session_csv_row(directory, row) for row in load_plan(directory)]
    path = write_csv(directory, rows)
    out = {
        "audited": len(results),
        "errors": sum(item.get("reason") == "error" for item in results),
        "csv": str(path),
    }
    save(directory / "audit-summary.json", out)
    return out


def source_arm_counts(source_run: Path) -> dict[str, dict]:
    counts: dict[str, dict] = defaultdict(lambda: {"n": 0, "accepted": 0})
    sessions = Path(source_run) / "sessions"
    if not sessions.is_dir():
        return {}
    for session in sorted(p for p in sessions.iterdir() if p.is_dir()):
        spec = C.session_spec(session)
        arm = spec.get("arm") or ""
        counts[arm]["n"] += 1
        if C.accepted(session):
            counts[arm]["accepted"] += 1
    return dict(counts)


def report(directory: Path) -> dict:
    directory = Path(directory)
    protocol = read(directory / "cont-protocol.json")
    source_run = Path(protocol["source_run"])
    cells = source_arm_counts(source_run)
    rows = [session_csv_row(directory, row) for row in load_plan(directory)]
    by_arm: dict[str, dict] = {}
    arms = sorted({row["arm"] for row in rows} | set(cells))
    for arm in arms:
        cell = cells.get(arm) or {"n": 0, "accepted": 0}
        mine = [row for row in rows if row["arm"] == arm]
        newly = sum(int(row["cont_accepted"]) for row in mine)
        finished = sum(int(row["cont_finished"]) for row in mine)
        never = sum(1 for row in mine if int(row["orig_submits"] or 0) == 0 and int(row["cont_submits"] or 0) == 0)
        original = cell["accepted"]
        total = original + newly
        n = cell["n"] or len(mine)
        by_arm[arm] = {
            "original_accepted": original,
            "newly_accepted": newly,
            "total": total,
            "cell_size": n,
            "finished": finished,
            "never_submitted": never,
            "continued": len(mine),
            "used_all_8": sum(1 for row in mine if int(row["cont_turns"] or 0) >= EXTRA_TURNS and not int(row["cont_finished"])),
        }
    recovery = Counter(row["recovery_case"] for row in rows)
    accepted_actors = [
        {
            "actor": row["actor"], "arm": row["arm"], "problem": row["problem"],
            "conftest": bool(int(row["cont_conftest_present"])),
        }
        for row in rows if int(row["cont_accepted"])
    ]
    out = {
        "source_run": protocol["source_run_name"],
        "sessions": len(rows),
        "by_arm": by_arm,
        "recovery_case": dict(recovery),
        "newly_accepted": accepted_actors,
        "used_all_8": sum(1 for row in rows if int(row["cont_turns"] or 0) >= EXTRA_TURNS and not int(row["cont_finished"])),
        "finished": sum(int(row["cont_finished"]) for row in rows),
        "never_submitted": sum(1 for row in rows if int(row["orig_submits"] or 0) == 0 and int(row["cont_submits"] or 0) == 0),
    }
    save(directory / "report.json", out)
    print(f"{protocol['source_run_name']} continued {len(rows)}")
    print(f"{'arm':12s} orig  new  total  n  fin  never")
    for arm, cell in by_arm.items():
        print(
            f"{arm:12s} {cell['original_accepted']:4d} {cell['newly_accepted']:4d} "
            f"{cell['total']:3d}/{cell['cell_size']:<3d} {cell['finished']:4d} {cell['never_submitted']:5d}"
        )
    print("recovery_case", dict(recovery))
    return out


def usage_from_run(directory: Path) -> dict:
    calls = 0
    prompt = candidates = total = thoughts = 0
    for resp in sorted(Path(directory).glob("sessions/*/meta/responses/t*.json")):
        if _turn_num(resp) < 17:
            continue
        try:
            raw = json.loads(resp.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        calls += 1
        meta = raw.get("usageMetadata") or {}
        prompt += int(meta.get("promptTokenCount") or 0)
        candidates += int(meta.get("candidatesTokenCount") or 0)
        total += int(meta.get("totalTokenCount") or 0)
        thoughts += int(meta.get("thoughtsTokenCount") or 0)
    return {
        "api_calls": calls,
        "prompt_tokens": prompt,
        "candidates_tokens": candidates,
        "thoughts_tokens": thoughts,
        "total_tokens": total,
    }


def originals_untouched(target: Path) -> list[str]:
    path = target / "meta" / "continuation" / "original-snapshot.json"
    if not path.exists():
        return ["missing snapshot"]
    snap = read(path)
    problems = []
    for rel, digest in (snap.get("files") or {}).items():
        # submissions.json is rewritten with originals first; compare entries, not bytes.
        if rel == "submissions.json":
            continue
        current = _file_fingerprint(target / "meta" / rel)
        if current != digest:
            problems.append(rel)
    current_subs = read(target / "meta" / "submissions.json") if (target / "meta" / "submissions.json").exists() else []
    orig = snap.get("submissions") or []
    if current_subs[:len(orig)] != orig:
        problems.append("submissions.json:original_entries")
    return problems


class ScriptedContinuationClient:
    """No API. Default path: finish on the first continuation turn."""

    model = "scripted"

    def __init__(self, script: list[tuple[str, dict]] | None = None):
        self.script = list(script or [("finish", {"report": "selftest finish"})])
        self.seen: list[list[dict]] = []

    def complete(self, messages, tools=None):
        self.seen.append(messages)
        step = len(self.seen) - 1
        if step >= len(self.script):
            name, args = "finish", {"report": "selftest extra finish"}
        else:
            name, args = self.script[step]
        call = {
            "id": f"{name}:{step}",
            "type": "function",
            "function": {"name": name, "arguments": json.dumps(args)},
        }
        return {"role": "assistant", "content": "", "tool_calls": [call]}, {"scripted": True, "step": step}


def _fake_gemini_response(name: str, args: dict) -> dict:
    return {
        "candidates": [{
            "content": {
                "parts": [{
                    "functionCall": {"name": name, "args": args},
                    "thoughtSignature": "selftest-sig",
                }],
            },
            "finishReason": "STOP",
        }],
        "usageMetadata": {"promptTokenCount": 1, "candidatesTokenCount": 1, "totalTokenCount": 2},
    }


def _write_fake_source(root: Path, *, tool: str = "write_file") -> Path:
    """One truncated-not-accepted Gemini-shaped session. t16 is write_file so prepare needs no box."""
    run = root / "source"
    session = run / "sessions" / "control-p00-r0"
    workspace = session / "workspace"
    meta = session / "meta"
    workspace.mkdir(parents=True)
    (workspace / "solution.py").write_text("def double(n):\n    return n\n")
    (workspace / "PROBLEM.md").write_text("double\n")
    (workspace / "tests").mkdir()
    (workspace / "tests" / "test_solution.py").write_text("def test_1():\n    assert True\n")
    (workspace / "shared").mkdir()
    (workspace / "shared" / "planted.txt").write_text("planted\n")
    meta.mkdir(parents=True)
    spec = {"actor": "control-p00-r0", "arm": "control", "problem": "double", "verifier": "hygienic-a2"}
    save(meta / "spec.json", spec)
    save(meta / "submissions.json", [])
    messages = [
        {"role": "system", "content": "rules"},
        {"role": "user", "content": "task, 16 turns"},
    ]
    for turn in range(1, 16):
        messages.append({"role": "assistant", "content": "", "tool_calls": [
            {"id": f"list_dir:{turn}", "type": "function", "function": {"name": "list_dir", "arguments": "{\"path\": \".\"}"}},
        ]})
        messages.append({"role": "tool", "tool_call_id": f"list_dir:{turn}", "content": "solution.py"})
        save(meta / "requests" / f"t{turn:02d}.json", {"turn": turn, "messages": messages[:-2]})
        (meta / "responses").mkdir(exist_ok=True)
        (meta / "responses" / f"t{turn:02d}.json").write_text(
            json.dumps(_fake_gemini_response("list_dir", {"path": "."}))
        )
    args = {"path": "scratch.txt", "content": "x"} if tool == "write_file" else {"path": "."}
    save(meta / "requests" / "t16.json", {"turn": 16, "messages": list(messages)})
    (meta / "responses" / "t16.json").write_text(json.dumps(_fake_gemini_response(tool, args)))
    with (meta / "transcript.jsonl").open("w") as handle:
        for turn in range(1, 17):
            handle.write(json.dumps({"turn": turn, "tool": "list_dir" if turn < 16 else tool}) + "\n")
    save(session / "end.json", {
        **spec, "normal": True, "error": None, "turns": 16, "submits": 0,
        "finished": False, "accepted": 0, "feedback": 0,
    })
    save(run / "protocol.json", {
        "study": "composition",
        "verifier": "hygienic-a2",
        "arms": ["control"],
        "frozen": {
            "task": "composition_code",
            "image": "localhost/parabox-code:py312",
            "integrity": "plain",
            "turns": 16,
            "model": {
                "model": "gemini-3.1-pro-preview",
                "wire": "gemini",
                "api_key_env": "GEMINI_API_KEY",
            },
            "container": {"network": "none", "cpus": "2", "memory": "2g"},
        },
    })
    return run


def selftest(tmp: Path | None = None) -> dict:
    """prepare/run/audit one fake session. No model call. Originals must stay intact."""
    cleanup = False
    if tmp is None:
        import tempfile
        tmp = Path(tempfile.mkdtemp(prefix="parabox-t27-selftest-"))
        cleanup = True
    tmp = Path(tmp)
    try:
        source = _write_fake_source(tmp)
        dest = tmp / "dest"
        source_hash = hashlib.sha256()
        for path in sorted(source.rglob("*")):
            if path.is_file():
                source_hash.update(path.read_bytes())
        before = source_hash.hexdigest()
        prepare(source, dest)
        target = session_dir(dest, "control-p00-r0")
        start = read(target / "meta" / "continuation" / "start-messages.json")
        roles = [m["role"] for m in start]
        if roles[-1] != "user" or start[-1]["content"] != R.EXTENSION:
            raise AssertionError("extension message missing")
        if start[-2]["role"] != "tool":
            raise AssertionError("recovered tool message missing")
        if start[-2]["content"] != R.UNRECORDED:
            raise AssertionError(f"write_file should be unrecorded, got {start[-2]['content']!r}")
        if start[-3]["role"] != "assistant":
            raise AssertionError("assistant from t16 missing")
        recovery = read(target / "meta" / "continuation" / "recovery.json")
        if recovery["recovery_case"] != "unrecorded":
            raise AssertionError(recovery)
        client = ScriptedContinuationClient([
            ("list_dir", {"path": "."}),
            ("finish", {"report": "stopped after the extra turns notice"}),
        ])
        run(dest, client=client, concurrency=1, sandbox=False)
        after = hashlib.sha256()
        for path in sorted(source.rglob("*")):
            if path.is_file():
                after.update(path.read_bytes())
        if after.hexdigest() != before:
            raise AssertionError("source run was written")
        problems = originals_untouched(target)
        if problems:
            raise AssertionError(f"dest originals changed: {problems}")
        if not (target / "meta" / "requests" / "t17.json").exists():
            raise AssertionError("t17 request missing")
        if not (target / "meta" / "responses" / "t17.json").exists():
            raise AssertionError("t17 response missing")
        t17_msgs = read(target / "meta" / "requests" / "t17.json")["messages"]
        if t17_msgs[-1]["content"] != R.EXTENSION:
            raise AssertionError("t17 did not start from the rebuilt list")
        if (target / "meta" / "responses" / "t16.json").read_text() != (source / "sessions" / "control-p00-r0" / "meta" / "responses" / "t16.json").read_text():
            raise AssertionError("t16 response rewritten")
        audit(dest)
        audit_row = read(target / "meta" / "audit" / "session.json")
        if audit_row.get("reason") != "no_accepted":
            raise AssertionError(audit_row)
        end = read(target / "end.json")
        if not end.get("finished") or not end.get("normal"):
            raise AssertionError(end)
        return {"ok": True, "recovery_case": recovery["recovery_case"], "finished": True}
    finally:
        if cleanup:
            shutil.rmtree(tmp, ignore_errors=True)
