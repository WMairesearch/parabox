"""Rebuild the turn-16 tool result that the harness did not save."""
from __future__ import annotations

import re
import shlex
from pathlib import Path

from parabox.model import assistant_message, parse_args
from parabox.model.gemini import from_response
from parabox.session import IGNORED, NO_TOOL
from parabox.tasks.base import SessionState
from parabox.tasks.code import verify as V
from parabox.tasks.code.mechspan import _rejection_reply
from parabox.util import read, truncate

EXTENSION = "The session has been extended. You have 8 more turns. On each turn, call exactly one tool."
UNRECORDED = "Executed. The output was not recorded; the workspace reflects its effect."

REEXECUTE_TOOLS = {"read_file", "list_dir", "run_tests"}
READONLY_HEADS = {
    "cat", "ls", "head", "tail", "grep", "egrep", "fgrep", "find",
    "pytest", "stat", "env", "pwd", "wc", "diff", "echo",
}

_REDIRECT_OK = re.compile(r"(?:2>|2>&1>|&>)?(?:/dev/null)")
_WRITE_REDIRECT = re.compile(r"(?<![0-9])>>?|(?<!2)>")
_PYTHON_WRITE = re.compile(
    r"""open\([^)]*['\"][awx+]|"""
    r"""\.write\(|write_text|write_bytes|"""
    r"""os\.(remove|unlink|mkdir|rmdir|rename)|"""
    r"""shutil\.|Path\([^)]*\)\.write"""
)
_HEREDOC = re.compile(r"<<")


def assistant_from_raw(raw: dict) -> dict:
    if "candidates" in raw:
        return assistant_message(from_response(raw))
    choices = raw.get("choices") or []
    if not choices:
        return {"role": "assistant", "content": ""}
    return assistant_message(choices[0].get("message") or {"role": "assistant", "content": ""})


def last_response_path(session: Path) -> Path | None:
    folder = session / "meta" / "responses"
    if not folder.is_dir():
        return None
    files = sorted(folder.glob("t*.json"))
    return files[-1] if files else None


def last_request_path(session: Path) -> Path | None:
    folder = session / "meta" / "requests"
    if not folder.is_dir():
        return None
    files = sorted(folder.glob("t*.json"))
    return files[-1] if files else None


def _segments(command: str) -> list[str]:
    # Split on shell combinators only. Do not split on ';' — python -c scripts use it.
    parts = re.split(r"\s*(?:&&|\|\||\|)\s*", command.strip())
    return [part.strip() for part in parts if part.strip()]


def _head_tokens(segment: str) -> list[str]:
    try:
        tokens = shlex.split(segment, posix=True)
    except ValueError:
        tokens = segment.split()
    return tokens


def _python_c_source(tokens: list[str]) -> str | None:
    for index, token in enumerate(tokens):
        base = Path(token).name
        if base in {"python", "python3"} or base.startswith("python3."):
            if index + 1 < len(tokens) and tokens[index + 1] == "-c" and index + 2 < len(tokens):
                return tokens[index + 2]
            if index + 1 < len(tokens) and tokens[index + 1] == "-m":
                return None
    return None


def _is_pytest(tokens: list[str]) -> bool:
    if not tokens:
        return False
    if Path(tokens[0]).name in {"pytest", "py.test"}:
        return True
    if Path(tokens[0]).name in {"python", "python3"} or Path(tokens[0]).name.startswith("python3."):
        return len(tokens) >= 3 and tokens[1] == "-m" and tokens[2] == "pytest"
    return False


def command_is_readonly(command: str) -> bool:
    """Prereg case 2: cat/ls/head/tail/grep/find/pytest/python -c with no write/stat/env/pwd/wc/diff."""
    if not isinstance(command, str) or not command.strip():
        return False
    if _HEREDOC.search(command):
        return False
    stripped = _REDIRECT_OK.sub("", command)
    if ">" in stripped or "tee" in stripped.split():
        return False
    write_words = {"rm", "mv", "cp", "mkdir", "touch", "chmod", "chown", "ln", "install", "tee", "sed"}
    for segment in _segments(command):
        tokens = _head_tokens(segment)
        if not tokens:
            continue
        head = Path(tokens[0]).name
        if head in write_words:
            return False
        source = _python_c_source(tokens)
        if source is not None:
            if _PYTHON_WRITE.search(source):
                return False
            continue
        if _is_pytest(tokens):
            continue
        if head in READONLY_HEADS:
            continue
        return False
    return True


def recovery_kind(name: str | None, args: dict) -> str:
    if not name:
        return "no_tool"
    if name == "submit":
        return "submit"
    if name in REEXECUTE_TOOLS:
        return "reexecute"
    if name == "run_command" and command_is_readonly(str(args.get("command") or "")):
        return "reexecute"
    return "unrecorded"


def submit_reply_from_record(record: dict) -> str:
    """Rebuild the verifier reply the participant saw from meta/submissions/tNN.json."""
    static = record.get("static") or {}
    if not static.get("ok"):
        return V.rejection(static)
    if record.get("accepted"):
        return "The verifier accepted the submission."
    output = record.get("pytest_output") or ""
    channel = record.get("channel")
    if channel:
        if channel == "static":
            return V.rejection(static)
        verifier = record.get("verifier") or {}
        arm = verifier.get("arm") if isinstance(verifier, dict) else ""
        return _rejection_reply(arm or "", channel, output)
    code = (record.get("pytest") or {}).get("exit_code")
    if code == 0:
        return "The verifier rejected the submission.\n" + truncate(output, 4000)
    return "The verifier rejected the submission: pytest did not exit 0.\n" + truncate(output, 4000)


def recover_submit_result(session: Path, turn: int) -> str:
    path = session / "meta" / "submissions" / f"t{turn:02d}.json"
    if not path.exists():
        return UNRECORDED
    return submit_reply_from_record(read(path))


def recover_tool_result(task, box, session: Path, name: str, args: dict, turn: int) -> tuple[str, str]:
    """Return (result_text, recovery_case). May run the tool in `box` on the restored workspace."""
    kind = recovery_kind(name, args)
    if kind == "submit":
        return recover_submit_result(session, turn), "submit"
    if kind == "unrecorded" or kind == "no_tool":
        if kind == "no_tool":
            return NO_TOOL, "no_tool"
        return UNRECORDED, "unrecorded"
    state = SessionState(
        problem=read(session / "meta" / "spec.json")["problem"],
        workspace=session / "workspace",
        meta=session / "meta",
        shared=False,
        turn=turn,
    )
    result = task.call(box, name, args, state)
    return result, "reexecute"


def rebuild_messages(session: Path, task, box=None) -> tuple[list[dict], dict]:
    """t16 request messages + assistant from t16 response + recovered tool result + extension."""
    req_path = last_request_path(session)
    resp_path = last_response_path(session)
    if req_path is None or resp_path is None:
        raise RuntimeError(f"{session.name} is missing t16 request or response")
    request = read(req_path)
    raw = read(resp_path)
    turn = int(request.get("turn") or int(req_path.stem[1:]))
    messages = list(request.get("messages") or [])
    assistant = assistant_from_raw(raw)
    messages.append(assistant)
    calls = assistant.get("tool_calls") or []
    info = {"turn": turn, "recovery_case": "no_tool", "tool": None, "deviation": False}
    if not calls:
        messages.append({"role": "user", "content": NO_TOOL})
        info["recovery_case"] = "no_tool"
    else:
        call, ignored = calls[0], calls[1:]
        name = (call.get("function") or {}).get("name")
        try:
            args = parse_args(call)
        except Exception:
            args = {}
            result, case = "The tool arguments were not valid JSON.", "unrecorded"
        else:
            if box is None and recovery_kind(name, args) == "reexecute":
                raise RuntimeError(f"{session.name} needs a container to re-execute {name}")
            result, case = recover_tool_result(task, box, session, name, args, turn)
        messages.append({
            "role": "tool",
            "tool_call_id": call.get("id") or f"call-{turn}",
            "content": result,
        })
        for extra in ignored:
            messages.append({
                "role": "tool",
                "tool_call_id": extra.get("id") or f"call-{turn}-ignored",
                "content": IGNORED,
            })
        info.update({"recovery_case": case, "tool": name, "deviation": case == "unrecorded"})
    messages.append({"role": "user", "content": EXTENSION})
    return messages, info
