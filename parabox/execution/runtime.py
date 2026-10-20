"""Internal invocation lifecycle; topology callers validate inputs before admission."""

from __future__ import annotations

from pathlib import Path

from .artifacts import manifest


def execute_invocation(engine, ledger, invocation, incoming):
    if Path(invocation.directory).exists():
        raise ValueError("New execution requires a fresh directory")
    ledger.admit(invocation.key, spec=invocation.spec)
    ledger.mark(invocation.key, "started")
    try:
        outcome = engine(invocation, dict(incoming))
        manifest(outcome.files)
        ledger.mark(invocation.key, "completed", {"normal": outcome.end.get("normal")})
        return outcome
    except BaseException as error:
        ledger.mark(invocation.key, "failed", {"error_type": type(error).__name__})
        raise


def validate_invocations(invocations):
    keys = [invocation.key for invocation in invocations]
    directories = [str(Path(invocation.directory).resolve()) for invocation in invocations]
    if len(set(keys)) != len(keys) or len(set(directories)) != len(directories):
        raise ValueError("Invocation keys and directories must be unique")
    if any(Path(directory).exists() for directory in directories):
        raise ValueError("All execution directories must be fresh")
