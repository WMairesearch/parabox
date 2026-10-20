import hashlib
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from parabox.execution import CoreEngine, FrozenWikiEngine, Invocation, run_population


class EngineBoundaryTests(unittest.TestCase):
    def test_core_handoff_cannot_replace_assigned_task(self):
        called = []
        engine = CoreEngine(lambda invocation: called.append(invocation))
        with self.assertRaisesRegex(ValueError, "under shared"):
            engine(Invocation("actor", Path("unused"), {}), {"solution.py": b"replacement"})
        self.assertEqual(called, [])

    def test_wiki_package_paths_and_bound_injected_runner(self):
        for variant, module in FrozenWikiEngine.MODULES.items():
            with self.subTest(variant=variant), tempfile.TemporaryDirectory() as temporary:
                path = Path(temporary) / (module.replace(".", "/") + ".py")
                path.parent.mkdir(parents=True)
                path.write_bytes(b"frozen")
                runner = Mock(return_value={"normal": True, "shutdown_verified": True})
                engine = FrozenWikiEngine(
                    variant=variant,
                    frozen={str(path): hashlib.sha256(path.read_bytes()).hexdigest()},
                    runner=runner, exporter=lambda _: {"shared/wiki/note": b"new"},
                )
                for policy in ("population_all", "population_accepted"):
                    with self.assertRaisesRegex(ValueError, "does not support"):
                        run_population([], engine=engine, ledger=None, initial={}, policy=policy)
                runner.assert_not_called()
                invocation = Invocation("actor", Path(temporary) / "session", {}, {
                    "config": {}, "image": "offline", "files": {},
                    "deadline": "2099-01-01T00:00:00Z",
                })
                incoming = {"shared/wiki/old": b"old"}
                result = engine(invocation, incoming)
                self.assertEqual(result.files, {"shared/wiki/note": b"new"})
                self.assertEqual(runner.call_args.kwargs["incoming"], incoming)
                self.assertIsNot(runner.call_args.kwargs["incoming"], incoming)
                path.write_bytes(b"changed")
                with self.assertRaisesRegex(ValueError, "Frozen file changed"):
                    engine(invocation, incoming)
                self.assertEqual(runner.call_count, 1)

    def test_wiki_requires_actual_import_binding(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "parabox/tasks/wiki/episode.py"
            with self.assertRaisesRegex(ValueError, "actual imported engine path"):
                FrozenWikiEngine(variant="base", frozen={str(path): "0" * 64})

    def test_lazy_package_import_and_public_exporter_contract(self):
        root = Path(__file__).resolve().parents[1]
        path = root / "parabox/tasks/wiki/episode.py"
        runner = Mock(return_value={"normal": True, "shutdown_verified": True})
        exporter = Mock(return_value=({"export": "metadata"}, {"shared/wiki/note": b"new"}))
        engine = FrozenWikiEngine(variant="base", frozen={str(path): "0" * 64})
        invocation = Invocation("actor", Path("unused"), {}, {
            "config": {}, "image": "offline", "files": {},
            "deadline": "2099-01-01T00:00:00Z",
        })
        module = SimpleNamespace(__file__=str(path), run_episode=runner)
        with patch("parabox.execution.engines.verify_files") as verify, patch(
                "parabox.execution.engines.importlib.import_module", return_value=module) as load, patch.dict(
                sys.modules, {"parabox.benchmark.sources": SimpleNamespace(export_wiki=exporter)}):
            result = engine(invocation, {})
            self.assertEqual(result.files, {"shared/wiki/note": b"new"})
            verify.assert_called_once_with(engine.frozen)
            load.assert_called_once_with("parabox.tasks.wiki.episode")
            exporter.assert_called_once_with(invocation.directory)
            runner.return_value = {"normal": True, "shutdown_verified": False}
            with self.assertRaisesRegex(RuntimeError, "verified shutdown"):
                engine(invocation, {})
            self.assertEqual(exporter.call_count, 1)
            module.__file__ = "/different/parabox/tasks/wiki/episode.py"
            with self.assertRaisesRegex(ValueError, "not bound"):
                engine(invocation, {})


if __name__ == "__main__":
    unittest.main()
