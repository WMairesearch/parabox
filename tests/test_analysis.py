import csv
import tempfile
import unittest
from pathlib import Path

from parabox.analysis import chain_interval, independent_difference, late_chains, read_sessions


class SessionCsvTest(unittest.TestCase):
    def test_mixed_headers_preserve_unknown_and_skip_aggregate(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "rows.csv"
            with path.open("w", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerows([
                    ["row_kind", "actor", "accepted", "audit_ok", "cheat", "generation", "agent"],
                    ["session", "actor-1", "True", "", "False", "1", "0"],
                    ["row_kind", "model", "gate", "n", "cheat"],
                    ["cell", "example", "open", "1", "0"],
                ])
            rows = read_sessions(path)
        self.assertEqual(len(rows), 1)
        self.assertIsNone(rows[0]["audit_ok"])
        self.assertIs(rows[0]["accepted"], True)
        self.assertEqual(rows[0]["agent"], 0)


class ClusterTest(unittest.TestCase):
    def test_constant_clusters_and_independent_difference(self):
        self.assertEqual(chain_interval([1.0] * 5, draws=100)["low"], 1.0)
        difference = independent_difference([0.0] * 5, [1.0] * 5, draws=100)
        self.assertEqual(difference, {"difference": -1.0, "low": -1.0, "high": -1.0})

    def test_single_cluster_does_not_claim_an_interval(self):
        self.assertIsNone(chain_interval([0.5])["low"])
        self.assertIsNone(independent_difference([0.5], [0.5, 0.7])["high"])

    def test_reproducible_and_unpaired(self):
        first = independent_difference([0, 1, 0], [0, 1, 0], draws=1000)
        self.assertEqual(first, independent_difference([0, 1, 0], [0, 1, 0], draws=1000))
        self.assertLess(first["low"], 0)
        self.assertGreater(first["high"], 0)

    def test_missing_session_peer_exclusion_and_unknown(self):
        rows = [{"chain": "mixed-method-c00", "generation": generation, "agent": agent,
                 "normal": True, "accepted": True, "cheat": agent == 3,
                 "audit_unknown": False}
                for generation in (6, 7, 8) for agent in range(4)]
        self.assertEqual(late_chains(rows, chains=1)[0]["rate"], 0)
        rows[0]["audit_unknown"] = True
        result = late_chains(rows, chains=1)[0]
        self.assertIsNone(result["rate"])
        self.assertEqual(result["upper"], 1 / 9)
        self.assertFalse(late_chains(rows[1:], chains=1)[0]["complete"])


if __name__ == "__main__":
    unittest.main()
