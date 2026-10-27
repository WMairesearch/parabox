import json
import tempfile
import unittest
from pathlib import Path

from parabox.records.io import read_bundle, write_bundle
from parabox.records.schema import Bundle


class RecordsIOTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source = self.root / "source.json"
        self.source.write_text('{"value": 1}')
        builder = Bundle("study", "test", root=self.root)
        source = builder.source(self.source)
        builder.record("summary", kind="aggregate", evidence=[source.ref("/value")])
        self.bundle = builder.finish()
        self.output = self.root / "export.json"

    def test_export_roundtrip_checks_source_bindings(self):
        write_bundle(self.output, self.bundle)
        self.assertEqual(read_bundle(self.output, root=self.root), self.bundle)
        self.assertEqual(self.source.read_text(), '{"value": 1}')
        self.assertEqual(list(self.root.glob(".evidence-*")), [])

    def test_exports_never_overwrite_existing_sources_or_results(self):
        write_bundle(self.output, self.bundle)
        before = self.output.read_bytes()
        with self.assertRaises(FileExistsError):
            write_bundle(self.output, self.bundle)
        with self.assertRaises(FileExistsError):
            write_bundle(self.source, self.bundle)
        self.assertEqual(self.output.read_bytes(), before)
        self.assertEqual(self.source.read_text(), '{"value": 1}')
        self.assertEqual(list(self.root.glob(".evidence-*")), [])

    def test_tampered_source_is_not_silently_regraded(self):
        write_bundle(self.output, self.bundle)
        self.source.write_text('{"value": 2}')
        with self.assertRaisesRegex(ValueError, "source changed"):
            read_bundle(self.output, root=self.root)
        self.assertEqual(read_bundle(self.output, root=self.root, verify_sources=False), self.bundle)

    def test_bad_pointer_fails_full_verification(self):
        self.bundle["records"][0]["evidence"][0]["pointer"] = "/absent"
        write_bundle(self.output, self.bundle)
        with self.assertRaises(KeyError):
            read_bundle(self.output, root=self.root)

    def test_external_source_requires_explicit_opt_in(self):
        inside = self.root / "inside"
        inside.mkdir()
        builder = Bundle("external", "test", root=inside)
        source = builder.source(self.source)
        builder.record("summary", kind="aggregate", evidence=[source.ref("")])
        write_bundle(self.output, builder.finish())
        with self.assertRaisesRegex(ValueError, "allow_external"):
            read_bundle(self.output, root=inside)
        self.assertEqual(read_bundle(self.output, root=inside, allow_external=True)["study"], "external")

    def test_metadata_does_not_execute_imports_or_code(self):
        self.bundle["metadata"]["advice"] = "__import__('os').system('false')"
        write_bundle(self.output, self.bundle)
        self.assertEqual(json.loads(self.output.read_text())["metadata"], self.bundle["metadata"])


if __name__ == "__main__":
    unittest.main()
