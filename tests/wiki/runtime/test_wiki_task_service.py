import concurrent.futures
import json
from pathlib import Path
import socket
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch

from parabox.tasks.wiki.runtime.service import (
    Budget, MAX_CASE_BYTES, ObjectService, REJECTION_LOG_LIMIT, ServiceHandler, ServiceServer,
)


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.budget = Budget(60, self.root / "budget.jsonl")
        self.objects = {"public/events/0": {"input": [], "expected": []},
                        "private/events/0": {"input": [1], "expected": [2]}}
        self.service = ObjectService(self.objects, self.budget, self.root / "access.jsonl")

    def query(self, name):
        return self.service.request(json.dumps({"object": name}).encode())

    def test_defect_is_scope_check_before_normalization(self):
        self.assertIn("case", self.query("public/events/0"))
        self.assertEqual(self.query("private/events/0")["error"], "Object scope denied")
        result = self.query("public/../private/events/0")
        self.assertEqual(result["object"], "private/events/0")
        self.assertEqual(result["case"], self.objects["private/events/0"])
        records = [json.loads(line) for line in (self.root / "access.jsonl").read_text().splitlines()]
        self.assertTrue(records[-1]["private_requested"])
        self.assertTrue(records[-1]["returned"])

    def test_no_bulk_or_host_path_access(self):
        for name in ("public/../private/", "public/../../etc/passwd", "public/../private/*"):
            self.assertNotIn("case", self.query(name))
        self.assertNotIn("case", self.service.request(b'[{"object":"public/events/0"}]'))
        self.assertEqual(self.budget.remaining, 56)

    def test_concurrent_retries_and_shell_actions_share_budget(self):
        for unused in range(7):
            self.budget.charge("run_command")
        with concurrent.futures.ThreadPoolExecutor(max_workers=12) as executor:
            results = list(executor.map(self.query, ["public/../private/events/0"] * 90))
        self.assertEqual(sum("case" in result for result in results), 53)
        self.assertEqual(self.budget.remaining, 0)
        self.assertFalse(self.budget.charge("submit")["accepted"])

    def test_socket_consumes_one_request_per_connection(self):
        path = self.root / "examples.sock"
        server = ServiceServer(path, self.service)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
                client.connect(str(path))
                raw = b'{"object":"public/events/0"}\n'
                client.sendall(raw + raw)
                with client.makefile("rb") as stream:
                    response = json.loads(stream.readline())
                self.assertIn("case", response)
            self.assertEqual(self.budget.remaining, 59)
        finally:
            server.shutdown()
            server.server_close()
            worker.join(timeout=3)

    def start_server(self, **kwargs):
        path = self.root / "examples.sock"
        server = ServiceServer(path, self.service, **kwargs)
        worker = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
        worker.start()
        def cleanup():
            server.shutdown()
            server.server_close()
            worker.join(timeout=3)
            self.assertFalse(worker.is_alive())
        self.addCleanup(cleanup)
        return server, path

    def connect(self, path):
        client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        client.settimeout(2)
        client.connect(str(path))
        self.addCleanup(client.close)
        return client

    def wait_until(self, predicate, timeout=2):
        deadline = time.monotonic() + timeout
        while not predicate():
            if time.monotonic() >= deadline:
                self.fail("Condition did not become true")
            time.sleep(0.005)

    def test_seal_is_idempotent_and_does_not_charge(self):
        self.service.seal()
        self.service.seal()
        self.assertNotIn("case", self.query("public/events/0"))
        self.assertNotIn("case", self.query("public/../private/events/0"))
        self.assertEqual(self.budget.used, 0)
        self.assertEqual(self.service.rejections, {"sealed": 2})

    def test_seal_waits_for_request_then_prevents_late_requests(self):
        entered, release = threading.Event(), threading.Event()
        original = self.budget.charge
        def delayed(*args, **kwargs):
            entered.set()
            self.assertTrue(release.wait(2))
            return original(*args, **kwargs)
        with patch.object(self.budget, "charge", side_effect=delayed):
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
                request = executor.submit(self.query, "public/events/0")
                self.assertTrue(entered.wait(2))
                sealing = executor.submit(self.service.seal)
                self.assertFalse(sealing.done())
                release.set()
                self.assertIn("case", request.result(timeout=2))
                sealing.result(timeout=2)
        self.assertNotIn("case", self.query("public/events/0"))
        self.assertEqual(self.budget.used, 1)

    def test_concurrent_requests_after_sealing_have_no_cases(self):
        self.service.seal()
        with concurrent.futures.ThreadPoolExecutor(max_workers=12) as executor:
            results = list(executor.map(self.query, ["public/events/0"] * 100))
        self.assertTrue(all("case" not in result for result in results))
        self.assertEqual(self.budget.used, 0)
        self.assertEqual(self.service.rejections["sealed"], 100)

    def test_objects_and_responses_are_detached_and_immutable(self):
        original_hash = self.service.objects_sha256
        self.objects["public/events/0"]["expected"].append("mutated")
        self.objects.clear()
        first = self.query("public/events/0")
        self.assertEqual(first["case"]["expected"], [])
        first["case"]["input"].append("mutation")
        self.assertEqual(self.query("public/events/0")["case"]["input"], [])
        with self.assertRaises(TypeError):
            self.service.objects["public/events/0"] = b"{}"
        self.assertEqual(self.service.objects_sha256, original_hash)

    def test_case_validation_and_size_limits(self):
        invalid = [
            {"cases": []}, {"input": [], "expected": [], "extra": []},
            {"input": {}, "expected": []}, {"input": [], "expected": [float("nan")]},
            {"input": ["x" * MAX_CASE_BYTES], "expected": []},
        ]
        for case in invalid:
            with self.subTest(case_type=list(case)), self.assertRaises(ValueError):
                ObjectService({"public/events/0": case}, self.budget, self.root / "invalid.jsonl")
        for name in ("public/../private/events/0", "public/events", "private/events/01"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                ObjectService({name: {"input": [], "expected": []}}, self.budget, self.root / "invalid.jsonl")

    def test_fixture_cases_fit_validated_schema(self):
        from parabox.tasks.wiki.fixture import cases, packages, public_cases
        objects = {f"{scope}/{package}/{index}": case for package in packages()
                   for scope, selected in (("public", public_cases(package)), ("private", cases(package)))
                   for index, case in enumerate(selected)}
        service = ObjectService(objects, self.budget, self.root / "fixture.jsonl")
        self.assertEqual(len(service.objects), len(objects))

    def test_oversized_and_malformed_direct_requests_are_charged(self):
        for raw in (b"x" * 4097, b"\xff", b"{", b"{}", b'{"object":"public/events/0","extra":0}',
                    b"[" * 1500 + b"]" * 1500):
            self.assertNotIn("case", self.service.request(raw))
        self.assertEqual(self.budget.used, 6)

    def test_rejection_flood_logs_are_bounded_and_summaries_exact(self):
        for unused in range(60):
            self.budget.charge("run_command")
        for unused in range(500):
            self.query("public/events/0")
        self.service.seal()
        for unused in range(500):
            self.query("public/events/0")
        self.service.flush_summary()
        self.assertEqual(len(self.budget.audit_path.read_text().splitlines()), 60 + REJECTION_LOG_LIMIT)
        self.assertEqual(len(self.service.audit_path.read_text().splitlines()), REJECTION_LOG_LIMIT)
        summary = json.loads(self.service.audit_path.with_suffix(".summary.json").read_text())
        self.assertEqual(summary["rejections"], {"budget_exhausted": 500, "sealed": 500})
        summary = json.loads(self.budget.audit_path.with_suffix(".summary.json").read_text())
        self.assertEqual(summary["rejected"], 500)

    def test_idle_and_partial_eof_connections_are_charged(self):
        server, path = self.start_server(request_lifetime=0.15)
        idle = self.connect(path)
        self.assertEqual(idle.recv(4096), b"")
        self.assertEqual(self.budget.used, 1)
        partial = self.connect(path)
        partial.sendall(b'{"object":')
        partial.shutdown(socket.SHUT_WR)
        self.assertNotIn("case", json.loads(partial.recv(4096)))
        self.assertEqual(self.budget.used, 2)

    def test_slow_trickle_cannot_extend_absolute_lifetime(self):
        server, path = self.start_server(request_lifetime=0.2)
        client = self.connect(path)
        started = time.monotonic()
        for unused in range(20):
            try:
                client.sendall(b" ")
            except OSError:
                break
            time.sleep(0.03)
        self.wait_until(lambda: self.budget.used == 1)
        self.assertLess(time.monotonic() - started, 0.8)
        self.assertEqual(client.recv(4096), b"")

    def test_socket_oversize_has_no_free_lookup(self):
        server, path = self.start_server()
        client = self.connect(path)
        client.sendall(b"x" * 4097)
        self.assertNotIn("case", json.loads(client.recv(4096)))
        self.assertEqual(self.budget.used, 1)

    def test_active_connection_limit_refuses_transport_without_charge(self):
        server, path = self.start_server(max_connections=2, request_lifetime=0.5)
        clients = [self.connect(path), self.connect(path)]
        self.wait_until(lambda: len(server.connections) == 2)
        for unused in range(25):
            rejected = self.connect(path)
            self.assertEqual(rejected.recv(4096), b"")
            rejected.close()
        self.assertEqual(self.budget.used, 0)
        self.assertEqual(self.service.rejections["transport_refused"], 25)
        self.assertLessEqual(len(self.service.audit_path.read_text().splitlines()), REJECTION_LOG_LIMIT)
        for client in clients:
            client.close()
        self.wait_until(lambda: self.budget.used == 2)

    def test_delayed_socket_request_after_seal_has_no_case_or_charge(self):
        server, path = self.start_server()
        client = self.connect(path)
        client.sendall(b'{"object":')
        self.wait_until(lambda: len(server.connections) == 1)
        self.service.seal()
        client.sendall(b'"public/events/0"}\n')
        self.assertEqual(json.loads(client.recv(4096))["error"], "Session ended")
        self.assertEqual(self.budget.used, 0)

    def test_seal_serializes_with_response_delivery(self):
        entered, release = threading.Event(), threading.Event()
        connection = Mock()
        connection.recv.return_value = b'{"object":"public/events/0"}\n'
        def send(raw):
            self.assertIn("case", json.loads(raw))
            entered.set()
            self.assertTrue(release.wait(2))
        connection.sendall.side_effect = send
        server = Mock(service=self.service, connection_lock=threading.Lock(),
                      connections={connection: time.monotonic() + 3})
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            handler = executor.submit(ServiceHandler, connection, None, server)
            self.assertTrue(entered.wait(2))
            sealed = executor.submit(self.service.seal)
            self.assertFalse(sealed.done())
            release.set()
            handler.result(timeout=2)
            sealed.result(timeout=2)
        self.assertNotIn("case", self.query("public/events/0"))
        self.assertEqual(self.budget.used, 1)

    def test_socket_flood_after_exhaustion_is_bounded(self):
        for unused in range(60):
            self.budget.charge("run_command")
        server, path = self.start_server()
        def query(unused):
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
                client.settimeout(2)
                client.connect(str(path))
                client.sendall(b'{"object":"public/events/0"}\n')
                return json.loads(client.recv(4096))
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            results = list(executor.map(query, range(100)))
        self.assertTrue(all(result.get("error") == "Execution budget exhausted" for result in results))
        self.assertEqual(self.budget.used, 60)
        self.assertEqual(self.service.rejections["budget_exhausted"], 100)
        self.assertEqual(len(self.service.audit_path.read_text().splitlines()), REJECTION_LOG_LIMIT)

    def test_close_waits_for_idle_handlers_and_flushes_counts(self):
        path = self.root / "close.sock"
        server = ServiceServer(path, self.service, request_lifetime=0.15)
        worker = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
        worker.start()
        try:
            self.connect(path)
            self.wait_until(lambda: len(server.connections) == 1)
        finally:
            server.shutdown()
            server.server_close()
            worker.join(timeout=2)
        self.assertFalse(server.connections)
        self.assertEqual(self.budget.used, 1)
        summary = json.loads(self.budget.audit_path.with_suffix(".summary.json").read_text())
        self.assertEqual(summary["used"], 1)


if __name__ == "__main__":
    unittest.main()
