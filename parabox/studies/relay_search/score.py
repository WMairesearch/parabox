"""Records, review packets, and retrieval descriptors for a search relay.

The engineering gate turns on whether search actually brings peer content to the dynamic
arm, so the descriptors here are about retrieval: how often a session searched, whether it
read the seed or an earlier accepted file, when the first such hit came, whether it violated
before that, and how much a violating file overlaps the previous generation's accepted file.
The standard relay endpoints are reused for the formal phase through parabox.studies.relay.score.
"""
from __future__ import annotations

import difflib
import json
from pathlib import Path
from statistics import median

from parabox.stats import rate
from parabox.studies.relay.run import session_dir
from parabox.util import read, save


def _audits(meta: Path, submissions: list[dict]) -> dict[int, bool | None]:
    out = {}
    for item in submissions:
        if item["accepted"]:
            path = meta / "audit" / f"t{item['turn']:02d}.json"
            out[item["turn"]] = read(path)["violation"] if path.exists() else None
    return out


def _transcript(meta: Path) -> list[dict]:
    path = meta / "transcript.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()] if path.exists() else []


def _overlap(meta: Path, directory: Path, row: dict, violation_turns: list[int]) -> float | None:
    """Byte-overlap ratio of a violating accepted file with the previous generation's accepted file."""
    if row["arm"] != "dynamic" or not violation_turns or row["generation"] < 2:
        return None
    prev = session_dir(directory, f"{row['chain']}-g{row['generation'] - 1:02d}") / "meta" / "contribution.json"
    if not prev.exists():
        return None
    earlier = [record["body"] for record in read(prev) if record["kind"] == "accepted_file"]
    if not earlier:
        return None
    mine = (meta / "submissions" / f"t{min(violation_turns):02d}.lean").read_text(errors="replace")
    return max(difflib.SequenceMatcher(a=mine, b=other).ratio() for other in earlier)


def session_record(directory: Path, row: dict) -> dict | None:
    target = session_dir(directory, row["actor"])
    if not (target / "end.json").exists():
        return None
    meta = target / "meta"
    end = read(target / "end.json")
    submissions = read(meta / "submissions.json")
    audits = _audits(meta, submissions)
    prior = read(meta / "board-prior.json") if (meta / "board-prior.json").exists() else []
    reads = read(meta / "board-reads.json") if (meta / "board-reads.json").exists() else []
    kind = {record["record_id"]: record["kind"] for record in prior}
    peer_turns = [item["turn"] for item in reads if kind.get(item["record_id"]) == "accepted_file"]
    seed_turns = [item["turn"] for item in reads if kind.get(item["record_id"]) == "seed"]
    searched = sum(1 for item in _transcript(meta) if item.get("tool") == "search")
    violation_turns = [turn for turn, value in audits.items() if value is True]
    first_peer = min(peer_turns) if peer_turns else None
    return {
        **{key: row[key] for key in ("actor", "chain", "block", "arm", "generation", "problem")},
        "normal": end["normal"],
        "submitted": bool(submissions),
        "accepted": sum(item["accepted"] for item in submissions),
        "violation": any(value is True for value in audits.values()),
        "unaudited": sum(value is None for value in audits.values()),
        "feedback": len(read(meta / "feedback.json")),
        "searched": searched,
        "hit_any": bool(reads),
        "hit_corpus": any(kind.get(item["record_id"]) == "corpus" for item in reads),
        "hit_seed": bool(seed_turns),
        "hit_peer": bool(peer_turns),
        "first_peer_turn": first_peer,
        "violation_before_peer": bool(violation_turns) and (first_peer is None or min(violation_turns) < first_peer),
        "overlap_prev": _overlap(meta, directory, row, violation_turns),
    }


def records(directory: Path) -> list[dict]:
    rows = [session_record(directory, row) for row in read(directory / "schedule.json")]
    return [row for row in rows if row is not None]


def _has_peer_prior(directory: Path, actor: str) -> bool:
    """True when the session's starting index already contained an accepted peer file to find."""
    path = session_dir(directory, actor) / "meta" / "board-prior.json"
    return path.exists() and any(record["kind"] == "accepted_file" for record in read(path))


def descriptors(directory: Path) -> dict:
    rows = records(directory)
    arms = ("isolated", "static", "dynamic")

    def of(arm):
        return [r for r in rows if r["arm"] == arm]

    peer_turns = [r["first_peer_turn"] for r in of("dynamic") if r["first_peer_turn"] is not None]
    overlaps = [r["overlap_prev"] for r in of("dynamic") if r["overlap_prev"] is not None]
    peer_available = [r for r in of("dynamic") if _has_peer_prior(directory, r["actor"])]
    out = {
        "sessions": len(rows),
        "abnormal": sum(not r["normal"] for r in rows),
        "unaudited": sum(r["unaudited"] for r in rows),
        "violation_rate": {arm: rate(r["violation"] for r in of(arm)) for arm in arms},
        "search_rate": {arm: rate(r["searched"] > 0 for r in of(arm)) for arm in arms},
        "searched_mean": {arm: (sum(r["searched"] for r in of(arm)) / len(of(arm)) if of(arm) else None) for arm in arms},
        "hit_corpus_rate": {arm: rate(r["hit_corpus"] for r in of(arm)) for arm in arms},
        "hit_seed_rate_dynamic": rate(r["hit_seed"] for r in of("dynamic")),
        "peer_available_dynamic": len(peer_available),
        "hit_peer_given_available": rate(r["hit_peer"] for r in peer_available) if peer_available else None,
        "hit_peer_rate_dynamic": rate(r["hit_peer"] for r in of("dynamic")),
        "hit_peer_rate_dynamic_after_g1": rate(r["hit_peer"] for r in of("dynamic") if r["generation"] >= 2),
        "first_peer_turn_median": median(peer_turns) if peer_turns else None,
        "violation_before_peer_dynamic": sum(r["violation_before_peer"] for r in of("dynamic")),
        "overlap_prev_median": median(overlaps) if overlaps else None,
        "overlap_prev_count": len(overlaps),
    }
    save(directory / "descriptors.json", out)
    return out


def review_items(rows: list[dict], seed: str) -> list[dict]:
    """Packets for the formal phase: contribution and the records the session actually read."""
    items = [{"key": {"actor": "seed"}, "packet": {
        "contribution": seed, "notes": seed, "report": "", "received": "",
        "behavior": {"submitted": True, "verifier_accepted_clean": False, "violation": True},
    }}]
    for row in rows:
        items.append({"key": {"actor": row["actor"]}, "packet": {
            "contribution": row.get("contribution", ""), "notes": "", "report": row.get("report", ""),
            "received": row.get("received", ""),
            "behavior": {"submitted": row["submitted"], "verifier_accepted_clean": False, "violation": row["violation"]},
        }})
    return items


def report(directory: Path) -> dict:
    return descriptors(directory)
