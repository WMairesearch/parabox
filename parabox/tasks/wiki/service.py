"""Externally metered synthetic object service for isolated participant sessions.

An admitted connection processes one request: newline, EOF, oversize, read error,
or absolute timeout all consume one unit while the service is open. Connections
refused at the active-connection limit are transport failures and cost no unit.
Sealed requests disclose no cases and consume no units. Budget-denied requests
consume no additional units. Rejection detail logs are capped; exact counters are
flushed at seal/close. A returned case records selection, not proof of reception.
"""
from __future__ import annotations

import json
from pathlib import Path
import posixpath
import re
import socketserver
import threading
import time
from types import MappingProxyType

from parabox.util import now, save, sha256


MAX_REQUEST_BYTES = 4096
MAX_CASE_BYTES = 32768
MAX_OBJECTS = 4096
MAX_OBJECT_BYTES = 16 * 1024 * 1024
REJECTION_LOG_LIMIT = 16
MAX_CONNECTIONS = 8
REQUEST_LIFETIME = 3.0


class Budget:
    def __init__(self, limit: int, audit_path: Path):
        if type(limit) is not int or limit < 1:
            raise ValueError("Positive integer budget required")
        self.limit = limit
        self.used = 0
        self.audit_path = audit_path
        self.lock = threading.Lock()
        self.rejected = 0
        audit_path.parent.mkdir(parents=True, exist_ok=True)

    @property
    def remaining(self) -> int:
        with self.lock:
            return self.limit - self.used

    def charge(self, kind: str, details: dict | None = None) -> dict:
        with self.lock:
            accepted = self.used < self.limit
            if accepted:
                self.used += 1
            record = {"at": now(), "kind": kind, "accepted": accepted,
                      "used": self.used, "remaining": self.limit - self.used,
                      "details": details or {}}
            if not accepted:
                self.rejected += 1
            if accepted or self.rejected <= REJECTION_LOG_LIMIT:
                with self.audit_path.open("a") as stream:
                    stream.write(json.dumps(record, sort_keys=True) + "\n")
            return record

    def flush_summary(self) -> None:
        with self.lock:
            save(self.audit_path.with_suffix(".summary.json"), {
                "used": self.used, "remaining": self.limit - self.used,
                "rejected": self.rejected, "rejection_log_limit": REJECTION_LOG_LIMIT})


class ObjectService:
    def __init__(self, objects: dict[str, dict], budget: Budget, audit_path: Path):
        if not isinstance(objects, dict) or len(objects) > MAX_OBJECTS:
            raise ValueError("Invalid object collection")
        frozen = {}
        total = 0
        for name, case in objects.items():
            if (not isinstance(name, str) or len(name) > 256
                    or not re.fullmatch(r"(?:public|private)/[A-Za-z0-9_-]+/(?:0|[1-9][0-9]*)", name)
                    or not isinstance(case, dict) or set(case) != {"input", "expected"}
                    or not isinstance(case["input"], list) or not isinstance(case["expected"], list)):
                raise ValueError("Expected a named single input/expected case")
            try:
                encoded = json.dumps(case, sort_keys=True, allow_nan=False).encode()
            except (TypeError, ValueError, RecursionError) as caught:
                raise ValueError("Case must be finite JSON") from caught
            total += len(encoded)
            if len(encoded) > MAX_CASE_BYTES or total > MAX_OBJECT_BYTES:
                raise ValueError("Case collection exceeds size limit")
            frozen[name] = encoded
        self.objects = MappingProxyType(frozen)
        self.objects_sha256 = sha256(json.dumps({name: sha256(raw) for name, raw in sorted(frozen.items())}))
        self.budget = budget
        self.audit_path = audit_path
        self.lock = threading.RLock()
        self.sealed = False
        self.rejections = {}
        audit_path.parent.mkdir(parents=True, exist_ok=True)

    def _reject(self, reason: str) -> None:
        self.rejections[reason] = self.rejections.get(reason, 0) + 1
        if sum(self.rejections.values()) <= REJECTION_LOG_LIMIT:
            with self.audit_path.open("a") as stream:
                stream.write(json.dumps({"at": now(), "rejection": reason, "returned": False}) + "\n")

    def transport_refused(self) -> None:
        with self.lock:
            self._reject("transport_refused")

    def flush_summary(self) -> None:
        with self.lock:
            save(self.audit_path.with_suffix(".summary.json"), {
                "sealed": self.sealed, "rejections": dict(self.rejections),
                "objects_sha256": self.objects_sha256,
                "rejection_log_limit": REJECTION_LOG_LIMIT})
            self.budget.flush_summary()

    def seal(self) -> None:
        """Wait for any in-flight request/delivery, then irreversibly deny cases."""
        with self.lock:
            self.sealed = True
            self.flush_summary()

    def request(self, raw: bytes) -> dict:
        with self.lock:
            if self.sealed:
                self._reject("sealed")
                return {"error": "Session ended", "remaining": self.budget.remaining}
            charge = self.budget.charge("example_request")
            if not charge["accepted"]:
                self._reject("budget_exhausted")
                return {"error": "Execution budget exhausted", "remaining": 0}
            requested = canonical = None
            response = {"error": "Invalid request"}
            try:
                if not isinstance(raw, bytes) or len(raw) > MAX_REQUEST_BYTES:
                    raise ValueError("Invalid request size")
                request = json.loads(raw)
                if (isinstance(request, dict) and set(request) == {"object"}
                        and isinstance(request["object"], str)
                        and len(request["object"]) <= 256):
                    requested = request["object"]
                    canonical = posixpath.normpath(requested)
                    if not requested.startswith("public/"):
                        response = {"error": "Object scope denied"}
                    elif canonical not in self.objects:
                        response = {"error": "Object not found"}
                    else:
                        response = {"object": canonical, "case": json.loads(self.objects[canonical])}
            except (ValueError, TypeError, UnicodeDecodeError, RecursionError):
                pass
            response["remaining"] = charge["remaining"]
            record = {"at": now(), "requested": requested, "canonical": canonical,
                      "private_requested": bool(canonical and canonical.startswith("private/")),
                      "returned": "case" in response, "response": response,
                      "budget_used": charge["used"]}
            with self.audit_path.open("a") as stream:
                stream.write(json.dumps(record, sort_keys=True) + "\n")
            return response


class ServiceServer(socketserver.ThreadingUnixStreamServer):
    daemon_threads = False
    block_on_close = True
    request_queue_size = MAX_CONNECTIONS

    def __init__(self, socket_path: Path, service: ObjectService, *,
                 max_connections: int = MAX_CONNECTIONS, request_lifetime: float = REQUEST_LIFETIME):
        if type(max_connections) is not int or not 1 <= max_connections <= MAX_CONNECTIONS:
            raise ValueError("Invalid connection limit")
        if not 0 < request_lifetime <= REQUEST_LIFETIME:
            raise ValueError("Invalid request lifetime")
        self.service = service
        self.socket_path = socket_path
        self.request_lifetime = request_lifetime
        self.slots = threading.BoundedSemaphore(max_connections)
        self.connections = {}
        self.connection_lock = threading.Lock()
        socket_path.parent.mkdir(parents=True, exist_ok=True)
        super().__init__(str(socket_path), ServiceHandler)
        socket_path.chmod(0o666)

    def process_request(self, request, client_address):
        if not self.slots.acquire(blocking=False):
            self.shutdown_request(request)
            self.service.transport_refused()
            return
        with self.connection_lock:
            self.connections[request] = time.monotonic() + self.request_lifetime
        try:
            super().process_request(request, client_address)
        except BaseException:
            self.release_request(request)
            raise

    def release_request(self, request):
        with self.connection_lock:
            self.connections.pop(request, None)
        self.slots.release()

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.release_request(request)

    def server_close(self):
        super().server_close()
        self.service.flush_summary()


class ServiceHandler(socketserver.BaseRequestHandler):
    def handle(self):
        with self.server.connection_lock:
            deadline = self.server.connections[self.request]
        raw = bytearray()
        try:
            while b"\n" not in raw and len(raw) <= MAX_REQUEST_BYTES:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError
                self.request.settimeout(remaining)
                chunk = self.request.recv(MAX_REQUEST_BYTES + 1 - len(raw))
                if not chunk:
                    raw = bytearray()
                    break
                raw.extend(chunk)
            raw = bytes(raw).split(b"\n", 1)[0]
        except (OSError, TimeoutError):
            raw = b""
        with self.server.service.lock:
            response = self.server.service.request(raw if time.monotonic() < deadline else b"")
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return
            try:
                self.request.settimeout(remaining)
                self.request.sendall((json.dumps(response) + "\n").encode())
            except OSError:
                return


CLIENT = '''import json
import socket
import sys

if len(sys.argv) != 2:
    raise SystemExit("Usage: python examples.py OBJECT")
with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
    connection.settimeout(5)
    connection.connect("/service/examples.sock")
    connection.sendall((json.dumps({"object": sys.argv[1]}) + "\\n").encode())
    with connection.makefile("rb") as stream:
        print(stream.readline(65536).decode(), end="")
'''
