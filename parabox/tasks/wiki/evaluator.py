"""Post-session JSON grading with expected answers kept outside candidate containers."""
from __future__ import annotations

import json
import math
from pathlib import Path
import selectors
import subprocess
import time
import uuid

from parabox.sandbox import Limits
from .runtime.helpers import FastBox as Box, _equal
from parabox.util import sha256


CASE_TIMEOUT = 5.0
OUTPUT_LIMIT = 65536
RUNNER = """import importlib.util, json, sys
spec = importlib.util.spec_from_file_location('candidate', '/candidate/solution.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
value = json.loads(sys.argv[1])
result = module.solve(value)
print(json.dumps(result, allow_nan=False))
"""


def _json_value(value) -> bool:
    if value is None or type(value) in (bool, int, str):
        return True
    if type(value) is float:
        return math.isfinite(value)
    if type(value) is list:
        return all(_json_value(item) for item in value)
    if type(value) is dict:
        return all(type(key) is str and _json_value(item) for key, item in value.items())
    return False




def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


def _execute(box: Box, value) -> dict:
    command = ["podman", "exec", box.name, "python", "-I", "-B", "-c", RUNNER,
               json.dumps(value, allow_nan=False, separators=(",", ":"))]
    output = {"stdout": bytearray(), "stderr": bytearray()}
    reason = None
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ, "stdout")
            selector.register(process.stderr, selectors.EVENT_READ, "stderr")
            deadline = time.monotonic() + CASE_TIMEOUT
            total = 0
            while selector.get_map():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    reason = "candidate_timeout"
                    break
                for key, _ in selector.select(min(remaining, 0.1)):
                    chunk = key.fileobj.read1(8192)
                    if not chunk:
                        selector.unregister(key.fileobj)
                        continue
                    retained = chunk[:max(0, OUTPUT_LIMIT - total)]
                    output[key.data].extend(retained)
                    total += len(chunk)
                    if total > OUTPUT_LIMIT:
                        reason = "candidate_output_limit"
                        break
                if reason:
                    break
            if reason:
                process.kill()
            try:
                process.wait(timeout=max(0.01, deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                reason = "candidate_timeout"
                process.kill()
                process.wait()
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
        process.stdout.close()
        process.stderr.close()
    decoded = {}
    for key, content in output.items():
        try:
            decoded[key] = bytes(content).decode("utf-8")
        except UnicodeDecodeError:
            decoded[key] = bytes(content).decode("utf-8", errors="ignore")
            reason = reason or "invalid_utf8_output"
    return {"exit_code": process.returncode, "reason": reason, **decoded}


def _stop_verified(box: Box) -> None:
    box.stop()
    check = subprocess.run(["podman", "container", "exists", box.name],
                           capture_output=True, timeout=10)
    if check.returncode != 1:
        raise RuntimeError(f"Container removal not verified: {box.name} (exists status {check.returncode})")


def _score(execution: dict, expected) -> dict:
    record = {**execution, "passed": False, "actual": None}
    if execution["reason"]:
        return record
    if execution["exit_code"] != 0:
        error = execution["stderr"]
        if error.startswith("Error:") and any(
                marker in error for marker in ("OCI", "crun:", "container", "cgroup.procs")):
            return {**record, "passed": None, "reason": "container_execution_error"}
        return {**record, "reason": "candidate_exception_or_exit"}
    try:
        actual = json.loads(execution["stdout"], object_pairs_hook=_object)
        if not _json_value(actual):
            raise ValueError("Non-finite or non-JSON result")
    except (ValueError, RecursionError):
        return {**record, "reason": "invalid_json_output"}
    matches = _equal(actual, expected)
    return {**record, "actual": actual, "passed": matches,
            "reason": "match" if matches else "wrong_answer"}


def evaluate(image: str, raw: bytes, cases: list[dict], scratch: Path) -> dict:
    """Grade immutable bytes; cleanup failure raises rather than returning a live sandbox.

    Cases and expected answers are never written to mounted files. Each case gets
    a fresh container and process; only its input enters the command. Empty or
    malformed suites are configuration errors, not vacuous passing submissions.
    """
    if not isinstance(raw, bytes) or not cases:
        raise ValueError("Expected candidate bytes and a nonempty fixed case list")
    if any(not isinstance(case, dict) or set(case) != {"input", "expected"}
           or not _json_value(case["input"]) or not _json_value(case["expected"]) for case in cases):
        raise ValueError("Each case must contain JSON input and expected values")
    scratch = Path(scratch)
    scratch.mkdir(parents=True, exist_ok=True)
    attempt = scratch / ("grade-" + uuid.uuid4().hex)
    candidate = attempt / "candidate"
    candidate.mkdir(parents=True)
    (candidate / "solution.py").write_bytes(raw)
    records = []
    infra_errors = []
    for index, case in enumerate(cases):
        box = Box("submission-grade-" + uuid.uuid4().hex, attempt / f"case-{index}", image,
                  Limits(cpus="1", memory="256m"), mounts=((str(candidate), "/candidate", "ro"),))
        try:
            box.start()
            record = _score(_execute(box, case["input"]), case["expected"])
        except (OSError, subprocess.SubprocessError) as error:
            record = {"passed": None, "actual": None, "reason": "infrastructure_error",
                      "detail": repr(error)}
        finally:
            _stop_verified(box)
        record["index"] = index
        records.append(record)
        if record["passed"] is None:
            infra_errors.append({"index": index, "reason": record["reason"]})
    passed = None if infra_errors else all(record["passed"] for record in records)
    return {"passed": passed, "cases": records, "codehash": sha256(raw),
            "infraerror": infra_errors or None}
