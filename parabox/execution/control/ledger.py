"""Persistent admission accounting; operation budgets remain engine-owned."""
from __future__ import annotations

from datetime import datetime, timezone
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import sqlite3


def verify_files(files: dict[str, str]) -> None:
    for name, expected in files.items():
        if hashlib.sha256(Path(name).read_bytes()).hexdigest() != expected:
            raise ValueError(f"Frozen file changed: {name}")


def spec_digest(spec: dict) -> str:
    if not isinstance(spec, dict):
        raise ValueError("Specification must be an object")
    raw = json.dumps(spec, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return hashlib.sha256(raw).hexdigest()


class StartLedger:
    """One durable reservation per invocation, including failed starts; no retries."""

    def __init__(self, path, *, cap: int, deadline: str, frozen: dict[str, str],
                 planned: dict[str, dict | str] | None = None):
        if type(cap) is not int or cap < 1 or not frozen:
            raise ValueError("Positive cap and nonempty frozen manifest required")
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.deadline = datetime.fromisoformat(deadline.replace("Z", "+00:00"))
        if self.deadline.tzinfo is None:
            raise ValueError("Deadline must include timezone")
        self.cap = cap
        self.frozen = {str(Path(name).resolve()): digest for name, digest in frozen.items()}
        self.planned = None
        if planned is not None:
            self.planned = {}
            for key, value in planned.items():
                digest = spec_digest(value) if isinstance(value, dict) else value
                if (not isinstance(key, str) or not key or not isinstance(digest, str)
                        or len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest)):
                    raise ValueError("Plan requires nonempty keys and specs or SHA256 digests")
                self.planned[key] = digest
        binding = json.dumps({"cap": cap, "deadline": self.deadline.isoformat(),
                              "frozen": self.frozen, "planned": self.planned}, sort_keys=True)
        with self._connect() as connection:
            connection.execute("CREATE TABLE IF NOT EXISTS binding (value TEXT NOT NULL)")
            connection.execute("CREATE TABLE IF NOT EXISTS starts "
                               "(key TEXT PRIMARY KEY, state TEXT NOT NULL, detail TEXT)")
            connection.execute("BEGIN IMMEDIATE")
            rows = connection.execute("SELECT value FROM binding").fetchall()
            if rows and rows != [(binding,)]:
                raise ValueError("Ledger configuration changed")
            if not rows:
                connection.execute("INSERT INTO binding VALUES (?)", (binding,))

    @contextmanager
    def _connect(self):
        connection = sqlite3.connect(self.path, timeout=30)
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def admit(self, key: str, *, spec: dict | None = None) -> None:
        if not isinstance(key, str) or not key:
            raise ValueError("Nonempty invocation key required")
        if self.planned is not None:
            if key not in self.planned or spec_digest(spec) != self.planned[key]:
                raise ValueError("Invocation does not match frozen plan")
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            verify_files(self.frozen)
            if datetime.now(timezone.utc) >= self.deadline:
                raise RuntimeError("Start deadline reached")
            if connection.execute("SELECT COUNT(*) FROM starts").fetchone()[0] >= self.cap:
                raise RuntimeError("Start cap reached")
            connection.execute("INSERT INTO starts VALUES (?, 'reserved', NULL)", (key,))

    def mark(self, key: str, state: str, detail=None) -> None:
        previous = {"started": "reserved", "completed": "started", "failed": "started"}
        if state not in previous:
            raise ValueError("Unsupported ledger transition")
        with self._connect() as connection:
            cursor = connection.execute(
                "UPDATE starts SET state=?, detail=? WHERE key=? AND state=?",
                (state, json.dumps(detail), key, previous[state]))
            if cursor.rowcount != 1:
                raise ValueError("Invalid ledger transition")

    def rows(self) -> list[dict]:
        with self._connect() as connection:
            return [{"key": key, "state": state, "detail": json.loads(detail) if detail else None}
                    for key, state, detail in connection.execute(
                        "SELECT key,state,detail FROM starts ORDER BY key")]
