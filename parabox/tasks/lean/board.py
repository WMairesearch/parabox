"""The Lean task with a message board that is read and written by tool call.

The board a session starts with comes from the study through SessionState.board_prior.
A note is on its author's board at once. A verifier-accepted file is not put on the
author's own board; contribution() returns it with the notes for the study to carry on.
shared=False is the isolated arm of the relay, unchanged: no board and no board tools.
style picks the participant text only; board behaviour is the same for both styles.
"""
from __future__ import annotations

import json

from parabox.sandbox import Box
from parabox.tasks.base import SessionState
from parabox.tasks.lean import prompts as P
from parabox.tasks.lean.task import LeanTask
from parabox.util import read, sha256, truncate

SEED_TITLE = "Seed recipe"
SHOWN = ("record_id", "seq", "kind", "generation", "title")
BOARD_TOOLS = ("board_list", "board_read", "board_write")


def make_record(seq: int, kind: str, generation: int, title: str, body: str, **hidden) -> dict:
    return {"record_id": f"record-{seq:04d}", "seq": seq, "kind": kind, "generation": generation,
            "title": title, "body": body, "body_sha256": sha256(body), **hidden}


def seed_record(body: str) -> dict:
    return make_record(1, "seed", 0, SEED_TITLE, body, author="seed", turn=0)


def accepted_title(generation: int, problem: str, turn: int) -> str:
    return f"Accepted file from generation {generation} ({problem}), turn {turn}"


def _whole(value, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value != int(value):
        raise ValueError(f"{name} must be an integer.")
    return int(value)


class BoardLeanTask(LeanTask):
    def __init__(self, style: str = "described"):
        if style not in P.BOARD_STYLES:
            raise ValueError(f"unknown board style {style!r}")
        self.style = style

    def system(self, *, integrity: str, shared: bool) -> str:
        return P.board_system(integrity, self.style) if shared else P.system(integrity, False)

    def task(self, *, shared: bool) -> str:
        return P.board_task(self.style) if shared else P.task(False)

    def tools(self, *, shared: bool) -> list[dict]:
        return P.board_tools(self.style) if shared else P.tools(False)

    def prompts_record(self, *, integrity: str, shared: bool) -> dict:
        return P.board_record(integrity, self.style) if shared else P.record(integrity, False)

    def call(self, box: Box, name: str, args: dict, state: SessionState) -> str:
        if name in BOARD_TOOLS:
            if not state.shared:
                return f"Unknown tool {name}."
            try:
                return self._board(name, args, state)
            except ValueError as error:
                return str(error)
        if name == "submit":
            args = {}
        return super().call(box, name, args, state)

    def _board(self, name: str, args: dict, state: SessionState) -> str:
        visible = state.board_prior + state.board_posts
        if name == "board_list":
            after = _whole(args.get("after_seq", 0), "after_seq")
            limit = _whole(args.get("limit", P.BOARD_LIST_MAX), "limit")
            if after < 0:
                raise ValueError("after_seq must be a nonnegative integer.")
            if not 1 <= limit <= P.BOARD_LIST_MAX:
                raise ValueError(f"limit must be 1..{P.BOARD_LIST_MAX}.")
            rows = [record for record in visible if record["seq"] > after]
            shown = [{key: record[key] for key in SHOWN} for record in rows[:limit]]
            return json.dumps({"records": shown, "more": len(rows) > limit}, ensure_ascii=False)
        if name == "board_read":
            record_id = args.get("record_id")
            match = next((record for record in visible if record["record_id"] == record_id), None)
            if match is None:
                raise ValueError(f"No record {record_id!r} is on the board.")
            own = any(post["record_id"] == record_id for post in state.board_posts)
            state.board_reads.append({"turn": state.turn, "record_id": record_id,
                                      "body_sha256": match["body_sha256"], "own": own})
            shown = {key: match[key] for key in SHOWN}
            shown["body"] = truncate(match["body"])
            return json.dumps({"record": shown}, ensure_ascii=False)
        title, body = args.get("title"), args.get("body")
        if not isinstance(title, str) or not 1 <= len(title) <= P.BOARD_TITLE_MAX:
            raise ValueError(f"title must contain 1..{P.BOARD_TITLE_MAX} characters.")
        if not isinstance(body, str) or not 1 <= len(body) <= P.BOARD_BODY_MAX:
            raise ValueError(f"body must contain 1..{P.BOARD_BODY_MAX} characters.")
        spec = read(state.meta / "spec.json")
        seq = max((record["seq"] for record in visible), default=0) + 1
        record = make_record(seq, "note", spec["generation"], title, body, author=spec["actor"], turn=state.turn)
        state.board_posts.append(record)
        return f"Saved as {record['record_id']}."

    def contribution(self, state: SessionState) -> list[dict]:
        """Board sessions add their notes, then one record per verifier-accepted file."""
        accepted = super().contribution(state)
        if not state.shared:
            return accepted
        spec = read(state.meta / "spec.json")
        records = [dict(post) for post in state.board_posts]
        seq = max((record["seq"] for record in state.board_prior + records), default=0)
        for item in accepted:
            seq += 1
            records.append(make_record(
                seq, "accepted_file", spec["generation"],
                accepted_title(spec["generation"], item["problem"], item["turn"]), item["file"],
                author=spec["actor"], turn=item["turn"], submission_sha256=item["sha256"],
            ))
        return records
