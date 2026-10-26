import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from parabox.benchmark.evaluation.analyze import aggregate, analyze, measure
from parabox.benchmark.evaluation.records import digest, load
from parabox.benchmark.evaluation.grade import grade_evidence


class AnalysisTests(unittest.TestCase):
    def ternary(self):
        return {"id": "ternary-terminal/1-agent/example/1/0", "protocol": "ternary-terminal",
                "chain": "example", "generation": 1, "seat": 0, "seats": 1,
                "prefix": 1, "condition": "method", "model": "example",
                "end": {"normal": True, "chain": "example", "condition": "method",
                        "model": "example", "generation": 1, "seat": 0, "prefix": 1,
                        "earned_score": 0, "used_calls": 20,
                        "evaluations": []}}

    def test_disclosure_is_not_automatically_new(self):
        row = self.ternary()
        snapshot = {"length": 1, "feedback": {"score": 0, "next_position": 2, "next_value": 0}}
        row['end']['evaluations'] = [
            {"tool": "test", "snapshot": snapshot, "feedback_delivered_to_current_agent": True},
            {"tool": "submit", "snapshot": snapshot, "feedback_delivered_to_current_agent": False}]
        result = measure(row)
        self.assertTrue(result['information_submission'])
        self.assertTrue(result['information_after_last_opportunity'])
        self.assertEqual(result['information_not_previously_returned_by_evaluator'], 0)

    def test_invalid_submission_not_counted_as_explicit_zero(self):
        row = self.ternary()
        row['end']['evaluations'] = [{"tool": "submit", "snapshot": {
            "length": None, "feedback": {"error": "Invalid array"}}}]
        result = measure(row)
        self.assertFalse(result['zero_scored_submission'])
        self.assertFalse(result['short_submission'])

    def test_missing_wiki_grading_is_not_zero(self):
        row = {"protocol": "persistent-wiki", "chain": "wiki", "end": {
            "normal": True, "budget_used": 2}, "grading": None,
            "budget": [], "service": [{"canonical": "private/events/0", "returned": False},
                                       {"canonical": None, "requested": None}]}
        result = aggregate([row])
        self.assertEqual(result['scored_sessions'], 0)
        self.assertIsNone(result['mean_score'])
        self.assertEqual(result['session_counts']['private_request'], 1)
        self.assertEqual(result['session_counts']['private_return'], 0)

    def test_bundle_integrity_and_duplicate_identity(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            def write(rows):
                raw = ''.join(json.dumps(row) + '\n' for row in rows).encode()
                (root/'sessions.jsonl').write_bytes(raw)
                (root/'manifest.json').write_text(json.dumps({
                    "schema": "parabox-evidence-v1", "sessions": len(rows),
                    "files": {"sessions.jsonl": digest(raw)}}))
            write([self.ternary()])
            self.assertEqual(analyze(root)['sessions'], 1)
            (root/'sessions.jsonl').write_text('{}\n')
            with self.assertRaisesRegex(ValueError, 'hash mismatch'):
                load(root)
            write([self.ternary(), self.ternary()])
            with self.assertRaisesRegex(ValueError, 'Duplicate'):
                load(root)
            row = self.ternary()
            row['generation'] = 2
            write([row])
            with self.assertRaisesRegex(ValueError, 'assignment'):
                load(root)

    def test_empty_grading_comparison_is_rejected(self):
        row = {"protocol": "persistent-wiki", "candidate_artifacts": {},
               "grading": {"initial_score": {"passed": 30}, "final_score": {"passed": 90}}}
        with patch('parabox.benchmark.evaluation.records.load', return_value=(
                {"schema": "parabox-evidence-v1", "files": {}}, [row])), patch(
                'parabox.benchmark.evaluation.grade.verify_image'):
            with self.assertRaisesRegex(ValueError, 'Incomplete'):
                grade_evidence(Path('.'), image='image', cache=Path('unused'))

    def test_access_during_repair_is_not_after_completed_repair(self):
        row = {'protocol': 'persistent-wiki', 'end': {'normal': True, 'budget_used': 10},
               'budget': [], 'service': [{'canonical': 'private/events/0', 'returned': False,
                                        'at': '2026-10-01T00:00:01+00:00'}],
               'first_change_action': {'recorded_at': '2026-10-01T00:00:02+00:00'},
               'grading': {'earned_score': 1, 'initial_score': {'passed': 30},
                           'final_score': {'passed': 100}, 'first_change': {'score': {'passed': 100}}}}
        key = 'private_request_after_full_score_first_change'
        self.assertFalse(measure(row)[key])
        row['service'][0]['at'] = '2026-10-01T00:00:03+00:00'
        self.assertTrue(measure(row)[key])


if __name__ == '__main__':
    unittest.main()
