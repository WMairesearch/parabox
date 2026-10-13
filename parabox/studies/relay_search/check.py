"""Replay what each search participant was sent and could retrieve.

Turn 1 carries the system text and the task text and nothing else. The starting index is
the frozen corpus for isolated, plus the seed for static, plus the chain's earlier accepted
files for dynamic, byte for byte. Every search hit is a record the session could see, every
accepted-file record is the verifier-accepted snapshot, and no feedback text reaches an index.
"""
from __future__ import annotations

from pathlib import Path

from parabox.studies.relay.run import load_seed, session_dir
from parabox.studies.relay_search.corpus import CORPUS_SHA, corpus_sha
from parabox.studies.relay_search.run import index_for
from parabox.tasks.lean.search import SearchLeanTask
from parabox.util import read, sha256

MIN_FEEDBACK_MATCH = 40


def check(directory: Path) -> dict:
    protocol = read(directory / "protocol.json")
    integrity = protocol["frozen"]["integrity"]
    task = SearchLeanTask()
    seed = load_seed()
    problems = []
    if protocol["frozen"].get("corpus_sha256") not in (None, CORPUS_SHA) or corpus_sha() != CORPUS_SHA:
        problems.append("corpus hash does not match the pinned value")
    indexes = {}
    feedback = []
    head = [
        {"role": "system", "content": task.system(integrity=integrity, shared=True)},
        {"role": "user", "content": task.task(shared=True)},
    ]
    for row in read(directory / "schedule.json"):
        target = session_dir(directory, row["actor"])
        if not (target / "end.json").exists():
            continue
        meta = target / "meta"
        actor, arm = row["actor"], row["arm"]
        if read(meta / "opening.json"):
            problems.append(f"{actor}: an opening message was sent")
        requests = sorted((meta / "requests").glob("t*.json"))
        if requests and read(requests[0])["messages"] != head:
            problems.append(f"{actor}: turn-1 request is not the system and task text alone")
        for path in requests:
            messages = read(path)["messages"]
            if messages[:len(head)] != head:
                problems.append(f"{actor} {path.stem}: opening changed")
            if len(messages) > 2 and messages[2]["role"] == "user":
                problems.append(f"{actor} {path.stem}: a user message follows the task text")
        prior = read(meta / "board-prior.json") if (meta / "board-prior.json").exists() else None
        expected = index_for(directory, row, seed)
        if prior != expected:
            problems.append(f"{actor}: starting index differs from the {arm} delivery")
        kinds = {record["kind"] for record in prior or []}
        if arm == "isolated" and kinds - {"corpus"}:
            problems.append(f"{actor}: isolated index is not the corpus alone")
        if arm == "static" and "accepted_file" in kinds:
            problems.append(f"{actor}: static index contains an accepted file")
        seen = {record["record_id"]: record["body_sha256"] for record in (prior or [])}
        for item in read(meta / "board-reads.json"):
            if seen.get(item["record_id"]) != item["body_sha256"]:
                problems.append(f"{actor}: turn {item['turn']} read a record it could not see")
        accepted = {item["turn"]: item for item in read(meta / "submissions.json") if item["accepted"]}
        for record in read(meta / "contribution.json"):
            if record["kind"] != "accepted_file":
                continue
            source = accepted.get(record["turn"])
            snap = meta / "submissions" / f"t{record['turn']:02d}.lean"
            if source is None or not snap.exists() or sha256(snap.read_bytes()) != record["submission_sha256"] \
                    or source["sha256"] != record["submission_sha256"]:
                problems.append(f"{actor}: accepted-file record at turn {record['turn']} is not the accepted snapshot")
        added = sorted(record["turn"] for record in read(meta / "contribution.json") if record["kind"] == "accepted_file")
        if added != sorted(accepted):
            problems.append(f"{actor}: contribution does not carry exactly the accepted files")
        indexes[actor] = "\n".join(record["body"] for record in (prior or []))
        feedback += [(actor, item["message"]) for item in read(meta / "feedback.json")
                     if isinstance(item.get("message"), str) and len(item["message"]) >= MIN_FEEDBACK_MATCH]
    for actor, text in indexes.items():
        for author, message in feedback:
            if message in text and message not in seed:
                problems.append(f"{actor}: index contains feedback from {author}")
    return {"sessions": sum(1 for _ in (directory / "sessions").glob("*/end.json")), "indexes": len(indexes),
            "problems": problems, "ok": not problems}
