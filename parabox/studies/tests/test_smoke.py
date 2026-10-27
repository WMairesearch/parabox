import unittest

from parabox.studies.costly_information.fixture import encode, evaluate, make_target
from parabox.studies.costly_information.run import default_spec as information_spec
from parabox.studies.costly_information.run import schedule
from parabox.studies.shared_wiki.design import build_plan, default_spec as wiki_spec
from parabox.studies.unified.design import design


class HistoricalStudySmokeTests(unittest.TestCase):
    def test_costly_information_schedule_and_feedback(self):
        spec = information_spec({"model": "model.json"}, "sha256:" + "a" * 64)
        spec["prefixes"] = [1]
        spec["generations"] = 2
        actors = schedule(spec)
        self.assertEqual(len(actors), 2)
        self.assertEqual([row["generation"] for row in actors], [1, 2])

        target = make_target(spec["seed"])
        self.assertEqual(evaluate(encode(target[:1]), target),
                         {"score": 0, "next_position": 2, "next_value": target[1]})

    def test_shared_wiki_successor_plan(self):
        spec = wiki_spec({"model": "model.json"}, "sha256:" + "a" * 64)
        spec.update(positions=2, scores=[30], conditions=["empty_wiki"], blocks=[0])
        rows = build_plan(spec)["sessions"]
        self.assertEqual(len(rows), 2)
        self.assertEqual([row["position"] for row in rows], [0, 1])
        self.assertEqual(len(rows[0]["successors"]), 1)

    def test_unified_chain_schedule(self):
        rows = design(mode="chain", arms=("control",), gate="open",
                      problems=("double",), lineages=1, generations=2)
        self.assertEqual(len(rows), 2)
        self.assertEqual({row["generation"] for row in rows}, {1, 2})


if __name__ == "__main__":
    unittest.main()
