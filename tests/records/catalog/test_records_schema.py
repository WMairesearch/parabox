import copy
import json
import tempfile
import unittest
from pathlib import Path

from parabox.records.schema import Bundle, parse, resolve_pointer, validate


class RecordsSchemaTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        (self.root / "saved.json").write_text(json.dumps({
            "rows": [{"actor": "recipient", "accepted": True, "violation": None}],
            "shared/note~old": "kept",
        }))
        self.builder = Bundle("study", "test", root=self.root)
        self.source = self.builder.source("saved.json")
        self.record = self.builder.record(
            "run/recipient", actor="recipient", run="run", role="recipient",
            evidence=[self.source.ref("/rows/0")], units={"chain": "run/chain"},
            status={"started": True, "ended": True, "normal": True},
        )

    def test_unknown_is_not_false_and_acceptance_is_not_cleanliness(self):
        self.builder.measure(self.record, "task.accepted", True, unit="boolean",
                             definition="Participant verifier acceptance",
                             evidence=[self.source.ref("/rows/0/accepted")])
        self.builder.measure(self.record, "behavior.accepted_invalid", None, unit="boolean",
                             definition="Independent audit of accepted submissions",
                             evidence=[self.source.ref("/rows/0/violation")])
        bundle = self.builder.finish()
        self.assertEqual(validate(bundle)["records"], 1)
        self.assertEqual(self.record["measurements"][1]["status"], "unknown")
        self.assertIsNone(self.record["canonical_key"])

    def test_summary_does_not_fabricate_episodes(self):
        self.builder.record("aggregate", kind="aggregate", role="summary",
                            evidence=[self.source.ref("")])
        self.assertEqual([record["kind"] for record in self.builder.finish()["records"]],
                         ["episode", "aggregate"])

    def test_observations_require_bound_existing_evidence(self):
        self.record["evidence"] = []
        with self.assertRaisesRegex(ValueError, "require evidence"):
            self.builder.finish()
        self.record["evidence"] = [{"source": self.source.id, "pointer": "/missing"}]
        with self.assertRaises(KeyError):
            self.builder.finish()

    def test_duplicate_canonical_episodes_are_not_extra_replication(self):
        self.record["canonical_key"] = "canonical"
        self.builder.record("other-view", actor="other", canonical_key="canonical",
                            evidence=[self.source.ref("/rows/0")])
        with self.assertRaisesRegex(ValueError, "Duplicate canonical"):
            self.builder.finish()

    def test_distinct_runs_can_reuse_actor_names(self):
        second = self.builder.record("second/recipient", actor="recipient",
                                     evidence=[self.source.ref("/rows/0")])
        self.assertNotEqual(self.record["id"], second["id"])
        self.assertEqual(validate(self.builder.finish())["records"], 2)

    def test_unknown_has_no_value_and_numeric_is_not_boolean(self):
        item = self.builder.measure(self.record, "private_requests", False, unit="count",
                                    definition="Requests outside assigned access scope",
                                    evidence=[self.source.ref("")])
        with self.assertRaisesRegex(ValueError, "not boolean"):
            self.builder.finish()
        item.update(value=0, status="unknown")
        with self.assertRaisesRegex(ValueError, "Only observed"):
            self.builder.finish()

    def test_event_order_and_restoration_remain_visible(self):
        self.builder.event(self.record, "artifact_change", 0,
                           attributes={"operation": "delete"}, evidence=[self.source.ref("")])
        self.builder.event(self.record, "artifact_change", 1,
                           attributes={"operation": "restore"}, evidence=[self.source.ref("")])
        self.assertEqual(validate(self.builder.finish())["events"], 2)
        self.record["events"][1]["sequence"] = 0
        with self.assertRaisesRegex(ValueError, "unique and increasing"):
            self.builder.finish()

    def test_relations_require_actual_records_and_evidence(self):
        successor = self.builder.record("next", actor="next", evidence=[self.source.ref("")])
        self.builder.relation(self.record, successor, "scheduled_successor",
                              evidence=[self.source.ref("")])
        self.assertEqual(validate(self.builder.finish())["relations"], 1)
        self.builder.data["relations"][0]["target"] = "not-a-record"
        with self.assertRaisesRegex(ValueError, "endpoints"):
            self.builder.finish()

    def test_aggregate_keys_and_source_identities_are_validated(self):
        bundle = copy.deepcopy(self.builder.finish())
        bundle["sources"][0]["sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "source identity"):
            validate(bundle)
        bundle = copy.deepcopy(self.builder.finish())
        bundle["schema_version"] = True
        with self.assertRaisesRegex(ValueError, "schema"):
            validate(bundle)

    def test_json_and_pointers_reject_ambiguous_nonfinite_data(self):
        self.assertEqual(resolve_pointer(self.source.data, "/shared~1note~0old"), "kept")
        for pointer in ("rows/0", "/rows/00", "/rows/-1", "/rows/0/~2", "/rows/0/~"):
            with self.subTest(pointer=pointer), self.assertRaises(ValueError):
                resolve_pointer(self.source.data, pointer)
        for text in ("NaN", "Infinity", "-Infinity"):
            with self.assertRaises(ValueError):
                parse(text.encode(), "json")

    def test_boolean_start_status_is_not_integer(self):
        self.record["status"]["started"] = 1
        with self.assertRaisesRegex(ValueError, "boolean or unknown"):
            self.builder.finish()
        self.record["status"]["started"] = False
        with self.assertRaisesRegex(ValueError, "cannot be unstarted"):
            self.builder.finish()

    def test_csv_evidence_uses_parsed_row_not_an_invented_json_file(self):
        (self.root / "saved.csv").write_text('actor,text\nrecipient,"two\nlines"\n')
        source = self.builder.source("saved.csv")
        self.assertEqual(resolve_pointer(source.data, "/1/1"), "two\nlines")
        self.assertEqual(source.ref("/1"), {"source": source.id, "pointer": "/1"})


if __name__ == "__main__":
    unittest.main()
