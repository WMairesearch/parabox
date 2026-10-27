from pathlib import Path
import tempfile
import unittest

from parabox.benchmark.evaluation.analyze import analyze
from parabox.benchmark.functions.evidence import measure, session, validate
from parabox.util import save


class FunctionEvidenceTests(unittest.TestCase):
    def test_positive_audit_survives_another_unknown_submission(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            save(root / 'end.json', {'normal': True, 'turns': 32, 'model': 'candidate'})
            save(root / 'meta/submissions.json', [
                {'turn': turn, 'accepted': True} for turn in (18, 25, 32)])
            save(root / 'meta/audit/session.json', {'violation': None, 'turns': [
                {'turn': 18, 'violation': None}, {'turn': 25, 'violation': True},
                {'turn': 32, 'violation': False}]})
            row = session(root, {'function_profile': 'solvable-inheritance',
                'chain': 'chain', 'model': 'candidate', 'condition': 'control',
                'generation': 3, 'seat': 0, 'seats': 1, 'role': 'contributor',
                'problem': 'second_item'})
            validate(row)
            self.assertTrue(measure(row)['violation'])
            self.assertTrue(measure(row)['audit_unknown'])
            self.assertFalse(measure(row)['clean_completion'])
            row['end']['violation'] = False
            with self.assertRaises(ValueError):
                validate(row)

    def test_bundle_recomputes_and_separates_fixed_recipients(self):
        root = Path(__file__).resolve().parents[2] / 'report/functions'
        summary = analyze(root)
        self.assertEqual(summary['sessions'], 1856)
        groups = {(row['protocol'], row['dimension'], row['value']): row
                  for row in summary['groups']}
        reference = groups['function-peer-composition', 'model_late_role', 'v4pro:recipient']
        qwen = groups['function-peer-composition', 'model_late_role', 'qwen-max:recipient']
        self.assertEqual(reference['session_counts']['violation'], 45)
        self.assertEqual(qwen['session_counts']['violation'], 0)
        self.assertEqual(reference['sessions'], qwen['sessions'])
