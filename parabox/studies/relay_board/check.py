"""Replay what each board-relay participant was sent and could read.

Turn 1 carries the system text and the task text and nothing else. A static board is the
seed alone; a dynamic board is the seed and the chain's earlier contributions, byte for
byte. Every board read returns a record the session could see. Every accepted-file record
is the verifier-accepted snapshot. No feedback text reaches a board.
"""
from __future__ import annotations

from pathlib import Path

from parabox.studies.relay import design as D
from parabox.studies.relay.run import load_seed, session_dir
from parabox.studies.relay_board.run import board_for, style_of
from parabox.tasks.lean.board import BoardLeanTask
from parabox.util import digest_json, read, sha256

ISOLATED_WORDS = ("board", "Board", "library", "Library", "later participant")
MIN_FEEDBACK_MATCH = 40


def check(directory: Path) -> dict:
    protocol = read(directory / "protocol.json")
    integrity = protocol["frozen"]["integrity"]
    task = BoardLeanTask(style_of(protocol))
    seed = load_seed()
    problems = []
    source = protocol.get("isolated_from")
    for actor, digest in (source or {}).get("sessions", {}).items():
        end = session_dir(directory, actor) / "end.json"
        if not end.exists() or digest_json(read(end)) != digest:
            problems.append(f"{actor}: isolated session is not the copy recorded in protocol.json")
    boards = {}
    feedback = []
    for row in read(directory / "schedule.json"):
        target = session_dir(directory, row["actor"])
        if not (target / "end.json").exists():
            continue
        meta = target / "meta"
        actor, arm = row["actor"], row["arm"]
        shared = D.SHARED[arm]
        head = [
            {"role": "system", "content": task.system(integrity=integrity, shared=shared)},
            {"role": "user", "content": task.task(shared=shared)},
        ]
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
        prior_path = meta / "board-prior.json"
        if arm == "isolated":
            visible = head[0]["content"] + head[1]["content"] + repr(task.tools(shared=False))
            problems += [f"{actor}: isolated text mentions {word!r}" for word in ISOLATED_WORDS if word in visible]
            if prior_path.exists():
                problems.append(f"{actor}: isolated session has a board")
        else:
            expected = board_for(directory, row, seed)
            prior = read(prior_path) if prior_path.exists() else None
            if prior != expected:
                problems.append(f"{actor}: starting board differs from the {arm} delivery")
            if arm == "static" and [record["kind"] for record in prior or []] != ["seed"]:
                problems.append(f"{actor}: static board is not the seed alone")
            posts = read(meta / "board-posts.json")
            seen = {record["record_id"]: record["body_sha256"] for record in (prior or []) + posts}
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
            added = [record["turn"] for record in read(meta / "contribution.json") if record["kind"] == "accepted_file"]
            if sorted(added) != sorted(accepted):
                problems.append(f"{actor}: contribution does not carry exactly the accepted files")
            boards[actor] = "\n".join(record["body"] for record in (prior or []) + posts)
        feedback += [(actor, item["message"]) for item in read(meta / "feedback.json")
                     if isinstance(item.get("message"), str) and len(item["message"]) >= MIN_FEEDBACK_MATCH]
    for actor, text in boards.items():
        for author, message in feedback:
            if message in text and message not in seed:
                problems.append(f"{actor}: board contains feedback from {author}")
    return {"sessions": sum(1 for _ in (directory / "sessions").glob("*/end.json")), "boards": len(boards),
            "problems": problems, "ok": not problems}
