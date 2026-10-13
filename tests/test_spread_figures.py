import hashlib
import importlib.util
import json
import math
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(importlib.util.find_spec("matplotlib"), "requires the report extra")
class SpreadFigureTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from scripts import spread_figures

        cls.figures = spread_figures

    def test_unknown_audit_is_a_gap_not_a_non_cheat(self):
        records = [{"accepted": True, "cheat": False, "audit_ok": False}]
        self.assertTrue(math.isnan(self.figures.cheating_rate(records)))

    def test_known_outcomes_keep_the_full_session_denominator(self):
        records = [
            {"accepted": True, "cheat": True, "audit_ok": False},
            {"accepted": True, "cheat": False, "audit_ok": True},
            {"accepted": False, "cheat": False, "audit_ok": False},
        ]
        self.assertAlmostEqual(self.figures.cheating_rate(records), 1 / 3)
        with self.assertRaises(ValueError):
            self.figures.cheating_rate([])

    def test_peer_endpoint_excludes_peers_and_matches_reported_counts(self):
        expected = {"v4pro": 45, "gemini": 18, "kimi": 18,
                    "qwen-max": 0, "ds-flash": 0, "qwen-flash": 0}
        for peer, records in self.figures.peer_records().items():
            self.assertEqual(len(records), 120)
            self.assertNotIn(3, {record["agent"] for record in records})
            late = [record for record in records if record["generation"] >= 6]
            self.assertEqual(len(late), 45)
            self.assertEqual(sum(record["cheat"] is True for record in late), expected[peer])
            self.assertEqual(sum(record["audit_ok"] is True and record["cheat"] is False
                                 for record in late), 45 - expected[peer])

    def test_inheritance_curve_marks_the_documented_unknown(self):
        records = self.figures.sessions("solvable-chains-gemini", "control")
        generation = [record for record in records if record["generation"] == 3]
        self.assertTrue(math.isnan(self.figures.cheating_rate(generation)))


class HandoffEvidenceTest(unittest.TestCase):
    def test_recorded_excerpt_is_the_one_displayed(self):
        evidence = json.loads((ROOT / "report/decks/spread-of-misalignment/evidence/relay-example.json").read_text())
        deck = (ROOT / "report/decks/spread-of-misalignment/short.tex").read_text()
        self.assertIn(evidence["outgoing_excerpt"], " ".join(deck.split()))
        self.assertTrue(evidence["author_audit_violation"])
        self.assertTrue(evidence["recipient_audit_violation"])
        self.assertEqual([step["tool"] for step in evidence["recipient_tool_steps"]],
                         ["read_file", "read_file", "read_file", "write_file", "submit"])

    def test_available_local_sources_match_the_recorded_digests(self):
        evidence = json.loads((ROOT / "report/decks/spread-of-misalignment/evidence/relay-example.json").read_text())
        available = [source for source in evidence["sources"] if (ROOT / source["path"]).is_file()]
        if not available:
            self.skipTest("Local transcript evidence is not present in this checkout")
        self.assertEqual(len(available), len(evidence["sources"]))
        for source in available:
            self.assertEqual(hashlib.sha256((ROOT / source["path"]).read_bytes()).hexdigest(),
                             source["sha256"])


if __name__ == "__main__":
    unittest.main()
