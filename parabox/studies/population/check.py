"""Replay what each population participant was sent and what landed on the record."""
from __future__ import annotations

from pathlib import Path

from parabox.studies.relay.run import session_dir
from parabox.studies.population import design as D
from parabox.studies.population.merge import final_accepted, merge_record, snapshot_shared
from parabox.studies.population.run import extra_files, record_snapshot, seed_files
from parabox.studies.transmission import notes as N
from parabox.studies.transmission.run import shared_digest
from parabox.studies.transmission.task import TASK, TransmissionCodeTask, forbidden_in_prompts
from parabox.util import read, sha256


def check(directory: Path) -> dict:
    protocol = read(directory / "protocol.json")
    task = TransmissionCodeTask()
    problems = []
    head = [
        {"role": "system", "content": task.system(integrity="plain", shared=False)},
        {"role": "user", "content": task.task(shared=False)},
    ]
    if head[1]["content"] != TASK:
        problems.append("task text is not the transmission task")
    if "list_dir" not in head[1]["content"]:
        problems.append("task text does not tell the participant to use list_dir")
    if "shared/" not in head[1]["content"]:
        problems.append("task text does not name the writable shared folder")
    if "later participants" not in head[1]["content"].lower():
        problems.append("task text does not address later participants")
    shown = head[0]["content"] + "\n" + head[1]["content"]
    for word in forbidden_in_prompts():
        if word in shown:
            problems.append(f"participant text contains {word}")
    if protocol.get("design_seed") != D.DESIGN_SEED:
        problems.append("design_seed is not the frozen T21 seed")
    sessions = 0
    by_cell: dict[tuple[str, int], list[dict]] = {}
    for row in read(directory / "schedule.json"):
        target = session_dir(directory, row["actor"])
        if not (target / "end.json").exists():
            continue
        sessions += 1
        meta, actor = target / "meta", row["actor"]
        if read(meta / "opening.json"):
            problems.append(f"{actor}: an opening message was sent")
        requests = sorted((meta / "requests").glob("t*.json"))
        if requests and read(requests[0])["messages"] != head:
            problems.append(f"{actor}: turn-1 request is not the system and task text alone")
        delivered = read(meta / "delivered.json")
        if delivered["arm"] != row["arm"]:
            problems.append(f"{actor}: delivered files are tagged for the wrong arm")
        want = extra_files(directory, row)
        got = {name: text.encode() for name, text in delivered["files"].items()}
        if got != want:
            problems.append(f"{actor}: delivered files differ from the carry-forward rule")
        if delivered.get("shared_sha256") and delivered["shared_sha256"] != shared_digest(got):
            problems.append(f"{actor}: recorded shared_sha256 does not match delivered files")
        if row["generation"] == 1:
            if delivered["files"] != {N.CONTROL_PATH: N.CONTROL}:
                problems.append(f"{actor}: generation-1 seed is not the control platform notice")
            if sha256(delivered["files"].get(N.CONTROL_PATH, "")) != sha256(N.CONTROL):
                problems.append(f"{actor}: generation-1 seed hash does not match the control notice")
            if seed_files() != {N.CONTROL_PATH: N.CONTROL.encode()}:
                problems.append("seed_files() is not the transmission control bytes")
        by_cell.setdefault((row["chain"], row["generation"]), []).append(row)

    for (chain, generation), rows in sorted(by_cell.items()):
        hashes = []
        for row in rows:
            delivered = read(session_dir(directory, row["actor"]) / "meta" / "delivered.json")
            hashes.append(delivered.get("shared_sha256"))
        if len(set(hashes)) != 1:
            problems.append(f"{chain} g{generation:02d}: agents did not receive byte-identical shared/")
        merge_file = directory / "merges" / f"{chain}-g{generation:02d}.json"
        if not merge_file.exists():
            problems.append(f"{chain} g{generation:02d}: missing merge log")
            continue
        logged = read(merge_file)
        received = extra_files(directory, rows[0])
        agents = []
        for row in rows:
            target = session_dir(directory, row["actor"])
            submissions = read(target / "meta" / "submissions.json") if (target / "meta" / "submissions.json").exists() else []
            agents.append({
                "agent": row["agent"],
                "actor": row["actor"],
                "accepted": final_accepted(submissions),
                "received": received,
                "written": snapshot_shared(target),
            })
        replay, _ = merge_record(received, agents, rows[0]["arm"])
        stored = record_snapshot(directory, chain, generation)
        if stored != replay:
            problems.append(f"{chain} g{generation:02d}: stored record differs from replayed merge")
        if logged.get("record_files") != {name: sha256(data) for name, data in sorted(replay.items())}:
            problems.append(f"{chain} g{generation:02d}: merge log file list does not match the record")
        if rows[0]["arm"] == "selected":
            accepted_by = {item["actor"]: item["accepted"] for item in agents}
            for item in logged.get("agents", []):
                actor = item["actor"]
                if actor in accepted_by and item.get("accepted") != accepted_by[actor]:
                    problems.append(f"{actor}: merge log accepted flag does not match submissions")
                if not item.get("accepted") and item.get("admitted"):
                    problems.append(f"{actor}: selected arm admitted files from an unaccepted author")
        next_rows = [r for r in read(directory / "schedule.json")
                     if r["chain"] == chain and r["generation"] == generation + 1]
        if next_rows and (session_dir(directory, next_rows[0]["actor"]) / "end.json").exists():
            nxt = read(session_dir(directory, next_rows[0]["actor"]) / "meta" / "delivered.json")
            nxt_files = {name: text.encode() for name, text in nxt["files"].items()}
            if nxt_files != stored:
                problems.append(f"{chain} g{generation + 1:02d}: delivered record is not the previous merge")

    return {"sessions": sessions, "problems": problems, "ok": not problems}
