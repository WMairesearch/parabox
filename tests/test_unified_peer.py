import unittest

from parabox.studies.unified.design import design
from parabox.studies.unified.notes import METHOD, PEER_PATH, seed_files
from parabox.studies.unified.run import arm_models
from pathlib import Path


class PeerDesignTest(unittest.TestCase):
    def test_conditions_option_preserves_legacy_compatibility(self):
        from parabox.studies.unified.__main__ import build_parser
        parser = build_parser()
        common = ["prepare", "example", "--mode", "single", "--gate", "open",
                  "--model", "example.json"]
        current = parser.parse_args(common + ["--conditions", "control,method"])
        legacy = parser.parse_args(common + ["--arms", "control,method"])
        self.assertEqual(current.arms, legacy.arms)
        import contextlib
        import io
        output = io.StringIO()
        with contextlib.redirect_stdout(output), self.assertRaises(SystemExit):
            parser.parse_args(["prepare", "--help"])
        self.assertIn("--conditions CONDITIONS", output.getvalue())
        self.assertNotIn("--arms", output.getvalue())

    def test_only_peer_seat_changes(self):
        recipient = Path("recipient.json")
        plans = []
        for peer in (Path("recipient.json"), Path("peer.json")):
            mapping = arm_models(["mixed-method"], recipient, [recipient] * 3 + [peer])
            plan = design(mode="population", arms=["mixed-method"], gate="open",
                          problems=["second_item"], chains=5, agents=4, generations=8,
                          seed=2026101101, models=mapping)
            self.assertEqual(len(plan), 160)
            self.assertEqual(sum(row["agent"] < 3 for row in plan), 120)
            self.assertTrue(all(row["merge"] == "all" for row in plan))
            for row in plan:
                self.assertEqual(row["model_config"], str(recipient if row["agent"] < 3 else peer))
            plans.append([{key: value for key, value in row.items()
                           if key not in ("model_config", "models")} for row in plan])
        self.assertEqual(plans[0], plans[1])

    def test_peer_arm_uses_method_not_default_location_hint(self):
        self.assertEqual(seed_files("mixed-method", "second_item", "open"),
                         {PEER_PATH: METHOD.encode()})


if __name__ == "__main__":
    unittest.main()
