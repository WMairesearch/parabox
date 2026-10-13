import unittest

from scripts.peer_analysis import summarize


def evidence(peer_cheats=False, recipient_cheats=False):
    return {"retry_starts": 0, "sessions": [
        {"chain": f"mixed-method-c{chain:02d}", "generation": generation,
         "agent": agent, "normal": True, "started": True, "accepted": True,
         "audit_unknown": False, "cheat": peer_cheats if agent == 3 else recipient_cheats}
        for chain in range(5) for generation in range(1, 9) for agent in range(4)
    ]}


class PrimaryEndpointTest(unittest.TestCase):
    def test_peer_cannot_arithmetically_change_recipient_endpoint(self):
        payload = {"reserved_retry_starts": 0,
                   "arms": {"v4pro": evidence(True), "alternative": evidence(False)}}
        result = summarize(payload, draws=100)
        self.assertEqual(result["arms"]["alternative"]["difference_from_v4pro"]["difference"], 0)
        self.assertEqual(result["arms"]["v4pro"]["peer"]["cheat"], 40)

    def test_missing_chain_has_bounds_and_not_a_zero_rate(self):
        alternative = evidence()
        for row in alternative["sessions"]:
            if row["chain"] == "mixed-method-c00" and row["generation"] >= 6:
                row["normal"] = None
                row["started"] = False
        result = summarize({"reserved_retry_starts": 0,
                            "arms": {"v4pro": evidence(), "alternative": alternative}}, draws=100)
        estimate = result["arms"]["alternative"]
        self.assertEqual(estimate["late_complete_known_chain_estimate"]["n_chains"], 4)
        self.assertEqual(estimate["planned_late_bounds"]["upper"], 0.2)


if __name__ == "__main__":
    unittest.main()
