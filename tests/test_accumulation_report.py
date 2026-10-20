import contextlib
import copy
import io
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

from scripts import accumulation_report as report


class AccumulationReportTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = report.load()
        cls.results = report.recompute(cls.data)

    def test_totals_and_exact_intervals(self):
        expected = {
            "gemini": {
                "sessions_per_condition": 60,
                "violations": {"isolated": 3, "static": 33, "dynamic": 47},
                "dynamic_minus_static": {
                    "value": 47 / 60 - 33 / 60,
                    "low": 0.06666666666666665,
                    "high": 0.38333333333333336,
                },
            },
            "deepseek": {
                "sessions_per_condition": 60,
                "violations": {"isolated": 0, "static": 11, "dynamic": 28},
                "dynamic_minus_static": {
                    "value": 28 / 60 - 11 / 60,
                    "low": 0.10000000000000003,
                    "high": 0.44999999999999996,
                },
            },
        }
        self.assertEqual(self.results, expected)
        report.check_expected(self.data, self.results)

    def test_record_order_does_not_change_bootstrap(self):
        data = copy.deepcopy(self.data)
        data["blocks"].reverse()
        self.assertEqual(report.recompute(data), self.results)

    def test_recomputation_uses_blocks_instead_of_expected_results(self):
        data = copy.deepcopy(self.data)
        data["blocks"][0]["violations"]["isolated"] = 1
        results = report.recompute(data)
        self.assertEqual(results["gemini"]["violations"]["isolated"], 4)
        with self.assertRaisesRegex(ValueError, "gemini.*differ"):
            report.check_expected(data, results)
        data = copy.deepcopy(self.data)
        data["expected"]["gemini"]["dynamic_minus_static"]["low"] = 0.05
        with self.assertRaisesRegex(ValueError, "gemini.*differ"):
            report.check_expected(data, self.results)

    def test_missing_duplicate_and_invalid_blocks_are_rejected(self):
        data = copy.deepcopy(self.data)
        data["blocks"].pop()
        with self.assertRaisesRegex(ValueError, "24 matched-block"):
            report.validate(data)
        data = copy.deepcopy(self.data)
        data["blocks"][1]["block"] = 0
        with self.assertRaisesRegex(ValueError, "Duplicate block"):
            report.validate(data)
        for value in (-1, 12, True, 1.0):
            with self.subTest(block=value):
                data = copy.deepcopy(self.data)
                data["blocks"][0]["block"] = value
                with self.assertRaisesRegex(ValueError, "block number"):
                    report.validate(data)
        data = copy.deepcopy(self.data)
        data["blocks"][0]["model"] = "unknown"
        with self.assertRaisesRegex(ValueError, "Unknown block model"):
            report.validate(data)

    def test_noninteger_and_out_of_range_counts_are_rejected(self):
        for value in (-1, 6, True, False, 1.0, "1", None):
            with self.subTest(count=value):
                data = copy.deepcopy(self.data)
                data["blocks"][0]["violations"]["dynamic"] = value
                with self.assertRaisesRegex(ValueError, "count.*integer in 0..5"):
                    report.validate(data)

    def test_conditions_and_denominators_are_required(self):
        for location in ("conditions", "block", "expected"):
            with self.subTest(location=location):
                data = copy.deepcopy(self.data)
                conditions = {
                    "conditions": data["conditions"],
                    "block": data["blocks"][0]["violations"],
                    "expected": data["expected"]["gemini"]["violations"],
                }[location]
                conditions["other"] = conditions.pop("static")
                with self.assertRaisesRegex(ValueError, "conditions"):
                    report.validate(data)
        for location in ("protocol", "block", "expected"):
            with self.subTest(denominator=location):
                data = copy.deepcopy(self.data)
                if location == "protocol":
                    data["protocol"]["sessions_per_model_condition"] = 59
                elif location == "block":
                    data["blocks"][0]["sessions_per_condition"] = 4
                else:
                    data["expected"]["gemini"]["sessions_per_condition"] = 59
                with self.assertRaisesRegex(ValueError, "sessions_per"):
                    report.validate(data)

    def test_changed_bootstrap_convention_is_rejected(self):
        for field, value in (("unit", "session"), ("seed", 1), ("draws", 1000),
                             ("quantile_indices", [499, 19499]), ("reset_rng_per_model", False)):
            with self.subTest(field=field):
                data = copy.deepcopy(self.data)
                data["bootstrap"][field] = value
                with self.assertRaisesRegex(ValueError, "bootstrap"):
                    report.validate(data)

    def test_source_bindings_are_allowlisted(self):
        for field, value in (("label", "private/source"), ("sha256", "not-a-digest")):
            with self.subTest(field=field):
                data = copy.deepcopy(self.data)
                data["source_files"][0][field] = value
                with self.assertRaises(ValueError):
                    report.validate(data)
        data = copy.deepcopy(self.data)
        data["source_files"][0]["path"] = "private/source"
        with self.assertRaisesRegex(ValueError, "source file"):
            report.validate(data)
        data = copy.deepcopy(self.data)
        data["protocol"]["participant_text"] = "Unexpected field"
        with self.assertRaisesRegex(ValueError, "protocol"):
            report.validate(data)
        serialized = json.dumps(self.data)
        self.assertNotIn("/home/", serialized)
        self.assertNotIn("runs/", serialized)

    def test_cli_outputs_recomputed_results_and_checks_expectations(self):
        with contextlib.redirect_stdout(io.StringIO()) as output:
            report.main([])
        self.assertEqual(json.loads(output.getvalue()), self.results)
        script = Path(report.__file__).resolve()
        result = subprocess.run(
            [sys.executable, "-I", "-B", str(script), "--check"],
            cwd=script.parent, capture_output=True, text=True, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("verified", result.stdout)
        data = copy.deepcopy(self.data)
        data["expected"]["gemini"]["violations"]["isolated"] = 4
        with patch.object(report, "load", return_value=data):
            with contextlib.redirect_stderr(io.StringIO()) as errors:
                with self.assertRaises(SystemExit) as raised:
                    report.main(["--check"])
        self.assertEqual(raised.exception.code, 2)
        self.assertIn("differ from expected", errors.getvalue())


if __name__ == "__main__":
    unittest.main()
