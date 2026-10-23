"""Sandbox lifecycle, immutable artifact and host comparison helpers."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import subprocess

from parabox.sandbox import Box
from parabox.util import now, save, sha256
from parabox.workspace import read_regular

STOP_TIMEOUT = 15
START_TIMEOUT = 30
EXISTS_TIMEOUT = 5


class FastBox(Box):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = self.name.replace("submission-grade-", "opportunity-grade-").replace(
            "submission-probe-", "opportunity-episode-")
        self.lifecycle = []

    def stop(self) -> None:
        record = {"name": self.name, "started_at": now(), "verified": False}
        try:
            removed = subprocess.run(["podman", "rm", "-f", "--time", "0", self.name],
                                     capture_output=True, text=True, timeout=STOP_TIMEOUT)
            record.update(returncode=removed.returncode, stdout=removed.stdout, stderr=removed.stderr)
        except (OSError, subprocess.SubprocessError) as error:
            record["removal_error"] = repr(error)
        try:
            exists = subprocess.run(["podman", "container", "exists", self.name],
                                    capture_output=True, text=True, timeout=EXISTS_TIMEOUT)
            record.update(exists_returncode=exists.returncode, exists_stderr=exists.stderr,
                          verified=exists.returncode == 1)
        except (OSError, subprocess.SubprocessError) as error:
            record["verification_error"] = repr(error)
        record["ended_at"] = now()
        self.lifecycle.append(record)
        save(self.workspace.parent / "lifecycle" / f"{self.name}.json", self.lifecycle)
        if not record["verified"]:
            raise RuntimeError(f"Container removal not verified: {self.name}; {record}")

    def start(self) -> None:
        self.workspace.mkdir(parents=True, exist_ok=True)
        for host, _destination, _options in self.mounts:
            Path(host).mkdir(parents=True, exist_ok=True)
        self.stop()
        subprocess.run(self.run_argv(), check=True, stdout=subprocess.DEVNULL,
                       stderr=subprocess.PIPE, timeout=START_TIMEOUT)


def fingerprints(files: dict[str, bytes]) -> dict[str, str]:
    return {name: sha256(raw) for name, raw in sorted(files.items())}

def before_deadline(deadline: str) -> bool:
    return datetime.now(timezone.utc) < datetime.fromisoformat(deadline)


def shutdown(box: Box) -> dict:
    box.stop()
    result = subprocess.run(["podman", "container", "exists", box.name], capture_output=True, text=True, timeout=10)
    verified = result.returncode == 1
    return {"verified": verified, "checked_at": now(), "exists_exit_code": result.returncode,
            "error": result.stderr[-2000:] if not verified else None}

def archive(meta: Path, raw: bytes) -> str:
    digest = sha256(raw)
    destination = meta / "artifacts" / digest
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not destination.exists():
        destination.write_bytes(raw)
    return digest

def snapshot_solution(workspace: Path, meta: Path) -> dict:
    try:
        raw = read_regular(workspace, "solution.py")
        return {"sha256": archive(meta, raw), "bytes": len(raw)}
    except FileNotFoundError:
        return {"sha256": None, "reason": "missing"}
    except ValueError as error:
        return {"sha256": None, "reason": "invalid_artifact", "detail": repr(error)}
    except OSError as error:
        return {"sha256": None, "reason": "artifact_io_error", "detail": repr(error)}


def _equal(actual, expected) -> bool:
    if type(actual) is not type(expected):
        return False
    if type(actual) is list:
        return len(actual) == len(expected) and all(
            _equal(left, right) for left, right in zip(actual, expected))
    if type(actual) is dict:
        return actual.keys() == expected.keys() and all(
            _equal(actual[key], expected[key]) for key in actual)
    return actual == expected
