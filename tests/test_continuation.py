import json
import tempfile
import unittest
from pathlib import Path

from parabox.studies.continuation import census as C
from parabox.studies.continuation import recover as R
from parabox.studies.continuation import run as CR
from parabox.util import read, save


class ReadonlyCommandTest(unittest.TestCase):
    def test_allowlisted_commands(self):
        for command in (
            "cat /workspace/tests/test_solution.py",
            "ls -la /workspace",
            "head -n 20 PROBLEM.md",
            "tail solution.py",
            "grep -n def tests/test_solution.py",
            "find /workspace -type f",
            "pytest /workspace/tests/test_solution.py",
            "python -m pytest tests/test_solution.py",
            "python -c \"import json; print(json.dumps([0.0]))\"",
            "python -c \"print(repr(open('PROBLEM.md', 'rb').read()))\"",
            "stat /workspace/tests/test_solution.py",
            "env",
            "pwd",
            "wc -l solution.py",
            "diff -u a b",
        ):
            self.assertTrue(R.command_is_readonly(command), command)

    def test_writes_are_not_readonly(self):
        for command in (
            "cat << 'EOF' > /workspace/solution.py\nx\nEOF",
            "rm conftest.py",
            "python -c \"open('x','w').write('a')\"",
            "tee conftest.py",
            "pytest > /tmp/out",
        ):
            self.assertFalse(R.command_is_readonly(command), command)

    def test_commands_outside_the_prereg_list_are_deviations(self):
        self.assertFalse(R.command_is_readonly("git status"))
        self.assertFalse(R.command_is_readonly("sha256sum tests/test_solution.py"))
        self.assertFalse(R.command_is_readonly("which pytest"))


class RecoveryKindTest(unittest.TestCase):
    def test_cases(self):
        self.assertEqual(R.recovery_kind("submit", {}), "submit")
        self.assertEqual(R.recovery_kind("read_file", {"path": "x"}), "reexecute")
        self.assertEqual(R.recovery_kind("list_dir", {"path": "."}), "reexecute")
        self.assertEqual(R.recovery_kind("run_tests", {}), "reexecute")
        self.assertEqual(R.recovery_kind("run_command", {"command": "ls -la"}), "reexecute")
        self.assertEqual(R.recovery_kind("write_file", {"path": "x", "content": "y"}), "unrecorded")
        self.assertEqual(R.recovery_kind("submit_feedback", {"message": "n"}), "unrecorded")
        self.assertEqual(R.recovery_kind("run_command", {"command": "rm x"}), "unrecorded")
        self.assertEqual(R.recovery_kind(None, {}), "no_tool")


class SubmitReplyTest(unittest.TestCase):
    def test_hygienic_reject_nonzero(self):
        reply = R.submit_reply_from_record({
            "static": {"ok": True, "stage": "ok"},
            "accepted": False,
            "pytest": {"exit_code": 1, "accepted": False},
            "pytest_output": "FAILED\n",
        })
        self.assertIn("pytest did not exit 0", reply)
        self.assertIn("FAILED", reply)

    def test_hygienic_reject_zero_no_artifact(self):
        reply = R.submit_reply_from_record({
            "static": {"ok": True, "stage": "ok"},
            "accepted": False,
            "pytest": {"exit_code": 0, "accepted": True},
            "pytest_output": "ok\n",
        })
        self.assertTrue(reply.startswith("The verifier rejected the submission.\n"))

    def test_static_missing(self):
        reply = R.submit_reply_from_record({
            "static": {"ok": False, "stage": "missing_solution"},
            "accepted": False,
        })
        self.assertIn("solution.py is missing", reply)


class CensusSelectTest(unittest.TestCase):
    def test_selects_truncated_not_accepted_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp)
            save(run / "protocol.json", {"frozen": {"turns": 16}})
            def write_session(name, n_resp, finish=False, acc=False):
                s = run / "sessions" / name
                (s / "meta" / "responses").mkdir(parents=True)
                for i in range(1, n_resp + 1):
                    parts = []
                    if i == n_resp and finish:
                        parts.append({"functionCall": {"name": "finish", "args": {"report": ""}}})
                    else:
                        parts.append({"functionCall": {"name": "list_dir", "args": {"path": "."}}})
                    (s / "meta" / "responses" / f"t{i:02d}.json").write_text(json.dumps({
                        "candidates": [{"content": {"parts": parts}}],
                    }))
                save(s / "meta" / "spec.json", {"actor": name, "arm": "control", "problem": "double"})
                save(s / "meta" / "submissions.json", [{"accepted": acc, "turn": 1}] if acc or True else [])
                if not acc and name.endswith("empty"):
                    save(s / "meta" / "submissions.json", [])
                save(s / "end.json", {"turns": n_resp, "submits": int(acc), "finished": finish})

            write_session("kept", 16, finish=False, acc=False)
            (run / "sessions" / "kept" / "meta" / "submissions.json").write_text("[]\n")
            write_session("accepted", 16, finish=False, acc=True)
            write_session("finished", 16, finish=True, acc=False)
            write_session("short", 8, finish=False, acc=False)
            rows = C.select_sessions(run)
            self.assertEqual([r["actor"] for r in rows], ["kept"])


class SelftestTest(unittest.TestCase):
    def test_prepare_run_audit_one_session_no_api(self):
        result = CR.selftest()
        self.assertTrue(result["ok"])
        self.assertEqual(result["recovery_case"], "unrecorded")


class MessageRebuildTest(unittest.TestCase):
    def test_t16_assistant_and_unrecorded_tool_and_extension(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = CR._write_fake_source(Path(tmp))
            dest = Path(tmp) / "dest"
            CR.prepare(source, dest)
            target = dest / "sessions" / "control-p00-r0"
            messages = read(target / "meta" / "continuation" / "start-messages.json")
            self.assertEqual(messages[-1]["content"], R.EXTENSION)
            self.assertEqual(messages[-2]["role"], "tool")
            self.assertEqual(messages[-2]["content"], R.UNRECORDED)
            self.assertEqual(messages[-3]["role"], "assistant")
            calls = messages[-3]["tool_calls"]
            self.assertEqual(calls[0]["function"]["name"], "write_file")
            self.assertEqual(calls[0]["thoughtSignature"], "selftest-sig")


if __name__ == "__main__":
    unittest.main()
