"""The Lean task with a BM25 search tool over a per-session reference index.

The index a session starts with arrives through SessionState.board_prior, the same channel
the board task uses, so replay and the delivery check are shared. search runs a local,
deterministic BM25 over that index and records every returned record as a read. The tool
and the participant text are identical for all arms; only the index content differs, so a
search returning results never reveals the arm. There is no write tool in this phase.
"""
from __future__ import annotations

import json

from parabox.retrieval import Bm25Index
from parabox.sandbox import Box
from parabox.tasks.base import SessionState
from parabox.tasks.lean import prompts as P
from parabox.tasks.lean.board import accepted_title, make_record
from parabox.tasks.lean.task import LeanTask
from parabox.util import read, truncate

SHOWN = ("record_id", "title")


class SearchLeanTask(LeanTask):
    def system(self, *, integrity: str, shared: bool) -> str:
        return P.search_system(integrity)

    def task(self, *, shared: bool) -> str:
        return P.search_task()

    def tools(self, *, shared: bool) -> list[dict]:
        return P.search_tools()

    def prompts_record(self, *, integrity: str, shared: bool) -> dict:
        return P.search_record(integrity)

    def call(self, box: Box, name: str, args: dict, state: SessionState) -> str:
        if name == "search":
            try:
                return self._search(args, state)
            except ValueError as error:
                return str(error)
        if name == "submit":
            args = {}
        return super().call(box, name, args, state)

    def _search(self, args: dict, state: SessionState) -> str:
        query = args.get("query")
        if not isinstance(query, str) or not query.strip():
            raise ValueError("query must be a nonempty string.")
        index = Bm25Index(state.board_prior)
        by_id = {record["record_id"]: record for record in state.board_prior}
        hits = index.search(query, P.SEARCH_RESULTS_MAX)
        results = []
        for rank, record_id in enumerate(hits, start=1):
            record = by_id[record_id]
            state.board_reads.append({"turn": state.turn, "record_id": record_id,
                                      "body_sha256": record["body_sha256"], "own": False,
                                      "query": query, "rank": rank})
            shown = {key: record[key] for key in SHOWN}
            shown["body"] = truncate(record["body"])
            results.append(shown)
        return json.dumps({"results": results}, ensure_ascii=False)

    def contribution(self, state: SessionState) -> list[dict]:
        """One accepted_file record per verifier-accepted file, for the next generation's index."""
        accepted = super().contribution(state)
        if not state.shared:
            return accepted
        spec = read(state.meta / "spec.json")
        records, seq = [], max((record["seq"] for record in state.board_prior), default=0)
        for item in accepted:
            seq += 1
            records.append(make_record(
                seq, "accepted_file", spec["generation"],
                accepted_title(spec["generation"], item["problem"], item["turn"]), item["file"],
                author=spec["actor"], turn=item["turn"], submission_sha256=item["sha256"],
            ))
        return records
