import copy
import tempfile
import unittest
from pathlib import Path

from parabox.records.query import select, summarize
from parabox.records.schema import Bundle


class RecordsQueryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        (root / "source.json").write_text("{}")
        self.builder = Bundle("study", "test", root=root)
        self.source = self.builder.source("source.json")

    def record(self, key, *, role="recipient", condition="empty", definition="Own score", value=1):
        record = self.builder.record(key, actor=key, role=role, model="model",
                                     run="run", assignment={"condition": condition},
                                     units={"chain": "shared-chain"}, evidence=[self.source.ref("")])
        self.builder.measure(record, "task.reward", value, unit="fraction",
                             definition=definition, evidence=[self.source.ref("")])
        return record

    def test_roles_and_conditions_are_never_pooled_by_default(self):
        self.record("first")
        self.record("second", role="source")
        self.record("third", condition="full")
        bundle = self.builder.finish()
        self.assertEqual(len(summarize(bundle)["groups"]), 3)
        self.assertEqual(len(select(bundle, role="recipient")), 2)
        self.assertEqual(len(select(bundle, condition="full")), 1)

    def test_shared_chain_and_unknown_reward_stay_visible(self):
        self.record("first")
        self.record("second", value=None)
        group = summarize(self.builder.finish())["groups"][0]
        self.assertEqual(group["records"], 2)
        self.assertEqual(group["units"]["chain"], {"distinct": 1, "missing": 0})
        measurement = group["measurements"][0]
        self.assertEqual(measurement["statuses"], {"observed": 1, "unknown": 1})
        self.assertEqual(measurement["mean"], 1)
        self.assertEqual(measurement["known"], 1)

    def test_same_metric_name_with_different_definition_is_not_merged(self):
        self.record("first", definition="Own submitted fraction", value=1)
        self.record("second", definition="Cases newly recovered", value=2)
        measurements = summarize(self.builder.finish())["groups"][0]["measurements"]
        self.assertEqual(len(measurements), 2)
        self.assertEqual([item["known"] for item in measurements], [1, 1])
        self.assertTrue(all(item["statuses"]["not_measured"] == 1 for item in measurements))

    def test_missing_metric_is_not_negative_behavior(self):
        record = self.record("first")
        self.record("second")
        self.builder.measure(record, "choice.inspect", False, unit="boolean",
                             definition="Executed terminal inspection", evidence=[self.source.ref("")])
        measurements = summarize(self.builder.finish())["groups"][0]["measurements"]
        inspect = next(item for item in measurements if item["name"] == "choice.inspect")
        self.assertEqual(inspect["false"], 1)
        self.assertEqual(inspect["statuses"]["not_measured"], 1)

    def test_subsets_cannot_inflate_or_replace_records(self):
        record = self.record("first")
        bundle = self.builder.finish()
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            summarize(bundle, records=[record, record])
        changed = copy.deepcopy(record)
        changed["measurements"][0]["value"] = 99
        with self.assertRaisesRegex(ValueError, "differs"):
            summarize(bundle, records=[changed])
        changed["id"] = "not-in-bundle"
        with self.assertRaisesRegex(ValueError, "belong"):
            summarize(bundle, records=[changed])
        self.assertEqual(summarize(bundle, records=[])["records"], 0)

    def test_started_filter_separates_unknown_from_explicit_unstarted(self):
        first = self.record("started")
        first["status"]["started"] = True
        second = self.record("cancelled")
        second["status"]["started"] = False
        self.record("unknown")
        bundle = self.builder.finish()
        for state, actor in (("true", "started"), ("false", "cancelled"), ("unknown", "unknown")):
            self.assertEqual([row["actor"] for row in select(bundle, started=state)], [actor])
        with self.assertRaises(ValueError):
            select(bundle, started="maybe")


if __name__ == "__main__":
    unittest.main()
