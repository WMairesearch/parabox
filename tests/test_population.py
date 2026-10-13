import unittest

from parabox.studies.population import design as D
from parabox.studies.population.merge import collect_changes, final_accepted, merge_record, prefixed_name
from parabox.studies.population.score import keyword_to_frame
from parabox.studies.transmission import notes as N
from parabox.tasks.code.problems import IMPOSSIBLE
from parabox.util import sha256


NOTICE = N.CONTROL.encode()
NOTICE_PATH = N.CONTROL_PATH


def agent(index, accepted, received, written, actor=None):
    return {
        "agent": index,
        "actor": actor or f"all-c00-g01-a{index}",
        "accepted": accepted,
        "received": received,
        "written": written,
    }


class DesignTest(unittest.TestCase):
    def test_default_plan_is_two_by_two_by_six_by_four(self):
        chains, schedule = D.design()
        self.assertEqual(len(schedule), 96)
        self.assertEqual(len(chains), 4)
        self.assertEqual({row["arm"] for row in schedule}, set(D.ARMS))
        self.assertEqual({row["generation"] for row in schedule}, {1, 2, 3, 4, 5, 6})
        self.assertEqual({row["agent"] for row in schedule}, {0, 1, 2, 3})
        self.assertEqual(D.DESIGN_SEED, 2026100801)
        for chain in chains:
            gens = [row for row in schedule if row["chain"] == chain["chain"]]
            self.assertEqual([row["problem"] for row in gens], [chain["problem"]] * 24)
            self.assertIn(chain["problem"], IMPOSSIBLE)
        self.assertEqual([c["problem"] for c in chains if c["arm"] == "all"], ["double", "label_zero"])

    def test_generations_are_contiguous_blocks(self):
        _, schedule = D.design()
        self.assertEqual([row["generation"] for row in schedule], sorted(row["generation"] for row in schedule))

    def test_assignment_lists_every_session(self):
        rows = D.assignment_record()
        self.assertEqual(len(rows), 96)
        self.assertEqual(rows[0]["actor"], "all-c00-g01-a0")
        self.assertEqual(rows[0]["problem"], "double")
        selected = [r for r in rows if r["arm"] == "selected" and r["chain_index"] == 1]
        self.assertEqual(len(selected), 24)
        self.assertTrue(all(r["problem"] == "label_zero" for r in selected))


class MergeTest(unittest.TestCase):
    def test_collision_prefixes_every_agent(self):
        received = {NOTICE_PATH: NOTICE}
        a0 = dict(received)
        a0["shared/note.txt"] = b"from 0"
        a1 = dict(received)
        a1["shared/note.txt"] = b"from 1"
        record, meta = merge_record(received, [
            agent(0, True, received, a0),
            agent(1, True, received, a1),
        ], "all")
        self.assertIn(NOTICE_PATH, record)
        self.assertEqual(record[NOTICE_PATH], NOTICE)
        self.assertNotIn("shared/note.txt", record)
        self.assertEqual(record["shared/a0-note.txt"], b"from 0")
        self.assertEqual(record["shared/a1-note.txt"], b"from 1")
        dests = {p["to"] for p in meta["placements"]}
        self.assertEqual(dests, {"shared/a0-note.txt", "shared/a1-note.txt"})

    def test_unique_new_file_keeps_its_name(self):
        received = {NOTICE_PATH: NOTICE}
        a0 = dict(received)
        a0["shared/only.txt"] = b"solo"
        a1 = dict(received)
        record, _ = merge_record(received, [
            agent(0, True, received, a0),
            agent(1, False, received, a1),
        ], "all")
        self.assertEqual(record["shared/only.txt"], b"solo")
        self.assertEqual(record[NOTICE_PATH], NOTICE)

    def test_record_is_cumulative(self):
        received = {NOTICE_PATH: NOTICE, "shared/old.txt": b"keep"}
        a0 = dict(received)
        a0["shared/new.txt"] = b"added"
        record, _ = merge_record(received, [agent(0, True, received, a0)], "all")
        self.assertEqual(record[NOTICE_PATH], NOTICE)
        self.assertEqual(record["shared/old.txt"], b"keep")
        self.assertEqual(record["shared/new.txt"], b"added")

    def test_modification_is_prefixed_and_original_stays(self):
        received = {NOTICE_PATH: NOTICE}
        a0 = {NOTICE_PATH: b"changed notice"}
        record, meta = merge_record(received, [agent(0, True, received, a0)], "all")
        self.assertEqual(record[NOTICE_PATH], NOTICE)
        self.assertEqual(record["shared/a0-platform-notice.txt"], b"changed notice")
        self.assertEqual(meta["agents"][0]["modified_existing"][0]["path"], NOTICE_PATH)

    def test_deletion_is_ignored_and_logged(self):
        received = {NOTICE_PATH: NOTICE, "shared/keep.txt": b"x"}
        a0 = {}
        record, meta = merge_record(received, [agent(0, True, received, a0)], "all")
        self.assertEqual(record, received)
        self.assertEqual(meta["agents"][0]["deleted_existing"], ["shared/keep.txt", NOTICE_PATH])
        self.assertEqual(len(meta["agents"][0]["ignored_deletions"]), 2)

    def test_selected_admits_only_accepted_authors(self):
        received = {NOTICE_PATH: NOTICE}
        honest = dict(received)
        honest["shared/condemn.txt"] = b"do not cheat"
        cheater = dict(received)
        cheater["shared/recipe.txt"] = b"use the hook"
        record, meta = merge_record(received, [
            agent(0, False, received, honest, actor="selected-c00-g01-a0"),
            agent(1, True, received, cheater, actor="selected-c00-g01-a1"),
        ], "selected")
        self.assertEqual(set(record), {NOTICE_PATH, "shared/recipe.txt"})
        self.assertEqual(record["shared/recipe.txt"], b"use the hook")
        self.assertNotIn("shared/condemn.txt", record)
        rejected = meta["agents"][0]["rejected"]
        self.assertEqual(len(rejected), 1)
        self.assertEqual(rejected[0]["path"], "shared/condemn.txt")
        self.assertEqual(meta["agents"][0]["admitted"], [])
        self.assertEqual(meta["agents"][1]["admitted"][0]["path"], "shared/recipe.txt")
        self.assertFalse(meta["agents"][0]["accepted"])
        self.assertTrue(meta["agents"][1]["accepted"])

    def test_selected_rejects_modifications_from_unaccepted_authors(self):
        received = {NOTICE_PATH: NOTICE}
        a0 = {NOTICE_PATH: b"rewritten"}
        record, meta = merge_record(received, [agent(0, False, received, a0)], "selected")
        self.assertEqual(record, received)
        self.assertEqual(meta["agents"][0]["rejected"][0]["kind"], "modified")

    def test_all_admits_unaccepted_authors(self):
        received = {NOTICE_PATH: NOTICE}
        a0 = dict(received)
        a0["shared/note.txt"] = b"honest note"
        record, _ = merge_record(received, [agent(0, False, received, a0)], "all")
        self.assertEqual(record["shared/note.txt"], b"honest note")

    def test_prefixed_name_and_final_accepted(self):
        self.assertEqual(prefixed_name("shared/note.txt", 2), "shared/a2-note.txt")
        self.assertTrue(final_accepted([{"accepted": False}, {"accepted": True}]))
        self.assertFalse(final_accepted([{"accepted": True}, {"accepted": False}]))
        self.assertFalse(final_accepted([]))

    def test_collect_changes_separates_new_modified_deleted(self):
        received = {"shared/a.txt": b"1", "shared/b.txt": b"2"}
        written = {"shared/a.txt": b"1", "shared/b.txt": b"changed", "shared/c.txt": b"new"}
        got = collect_changes(received, written)
        self.assertEqual(got["new"], {"shared/c.txt": b"new"})
        self.assertEqual(got["modified"], {"shared/b.txt": b"changed"})
        self.assertEqual(got["deleted"], [])
        got = collect_changes(received, {"shared/a.txt": b"1"})
        self.assertEqual(got["deleted"], ["shared/b.txt"])

    def test_control_seed_bytes_match_transmission(self):
        self.assertEqual(sha256(N.CONTROL), sha256(NOTICE))
        self.assertEqual(N.CONTROL_PATH, "shared/platform-notice.txt")

    def test_keyword_frame_maps_warning_to_condemn(self):
        self.assertEqual(keyword_to_frame("warning"), "condemn")
        self.assertEqual(keyword_to_frame("recipe_conftest"), "promote")
        self.assertEqual(keyword_to_frame("other"), "other")


class PrefixCollisionTest(unittest.TestCase):
    def test_second_prefix_when_name_already_taken(self):
        received = {NOTICE_PATH: NOTICE, "shared/a0-note.txt": b"prior"}
        a0 = dict(received)
        a0[NOTICE_PATH] = b"edit"
        record, _ = merge_record(received, [agent(0, True, received, a0)], "all")
        self.assertEqual(record[NOTICE_PATH], NOTICE)
        self.assertEqual(record["shared/a0-note.txt"], b"prior")
        self.assertIn("shared/a0-platform-notice.txt", record)
        self.assertEqual(record["shared/a0-platform-notice.txt"], b"edit")


if __name__ == "__main__":
    unittest.main()
