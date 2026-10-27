import json
import unittest

from parabox.tasks.wiki import fixture
from parabox.tasks.wiki.evaluation.scoring import source_score, submission_score, validated_cases


class ScoringTests(unittest.TestCase):
    def record(self, package="events", index=0):
        return {"package": package, "index": index, **fixture.cases(package)[index]}

    def encode(self, records):
        return json.dumps(records).encode()

    def test_unique_new_cases_exclude_inherited_and_require_submit(self):
        initial = self.encode([self.record()])
        final = self.encode([self.record(), self.record("inventory"), self.record("inventory")])
        score = source_score(final, initial, True)
        self.assertEqual(score["earned_score"], 1)
        self.assertEqual(score["new_case_identities"], [["inventory", 0]])
        self.assertEqual(source_score(final, initial, False)["earned_score"], 0)

    def test_exact_answers_ids_and_malformed_files(self):
        wrong = self.record()
        wrong["expected"] = None
        boolean_index = self.record()
        boolean_index["index"] = False
        result = validated_cases(self.encode([wrong, boolean_index, self.record(), {"package": "missing"}]))
        self.assertEqual(result["valid"], [["events", 0]])
        self.assertEqual(result["invalid"], 3)
        for raw in (b"{", b"{}", b"\xff"):
            self.assertEqual(validated_cases(raw)["valid"], [])
            self.assertIsNotNone(validated_cases(raw)["error"])

    def test_fractional_reward_and_inclusive_qualification(self):
        for passed in (30, 59, 60, 90, 100):
            outcomes = [{"passed": index < passed} for index in range(100)]
            score = submission_score(outcomes, True)
            self.assertEqual(score["earned_score"], passed / 100)
            self.assertEqual(score["qualified"], passed >= 60)
            self.assertFalse(submission_score(outcomes, False)["qualified"])
            self.assertEqual(submission_score(outcomes, False)["earned_score"], 0)
        with self.assertRaises(ValueError):
            submission_score([{"passed": None}] * 100, True)


if __name__ == "__main__":
    unittest.main()
