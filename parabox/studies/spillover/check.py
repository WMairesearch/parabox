"""Replay spillover prompts, seat table, and the carry-forward record."""
from __future__ import annotations

import json
from pathlib import Path

from parabox.studies.population.merge import final_accepted, merge_record, snapshot_shared
from parabox.studies.population.run import record_snapshot
from parabox.studies.relay.run import session_dir
from parabox.studies.spillover import design as D
from parabox.studies.spillover.run import extra_files, planted_record
from parabox.studies.spillover.task import CLAUSE_FROM, CLAUSE_TO, TASK, VERIFIER, SpilloverTask
from parabox.studies.transmission.run import shared_digest
from parabox.studies.transmission.task import TASK as TRANSMISSION_TASK
from parabox.tasks.code.problems import IMPOSSIBLE, POSSIBLE
from parabox.tasks.code.task import CACHE_DIR
from parabox.util import read, sha256

FORBIDDEN = ("conftest", CACHE_DIR, "K7", "condemn", "DeepSeek")
LEGACY_VERIFIER = "hygienic-mixed"


def _protocol_verifier(protocol: dict) -> str:
    return protocol.get("verifier") or protocol.get("frozen", {}).get("verifier") or VERIFIER


def _payload_text(payload: dict) -> str:
    tools = payload.get("tools")
    return "\n".join([
        str(payload.get("system") or ""),
        str(payload.get("task") or ""),
        json.dumps(tools, ensure_ascii=False) if tools is not None else "",
    ])


def _prompt_problems(payload: dict, prefix: str) -> list[str]:
    problems = []
    shown = _payload_text(payload)
    for word in FORBIDDEN:
        if word in shown:
            problems.append(f"{prefix} contains {word}")
    return problems


def _seat_problems(schedule: list[dict], verifier: str) -> list[str]:
    problems = []
    for row in schedule:
        index = row["chain_index"]
        seat = row["seat"]
        if index not in D.CHAIN_PROBLEMS or seat >= len(D.CHAIN_PROBLEMS[index]):
            problems.append(f"{row['actor']}: seat/chain is outside the preregistration table")
            continue
        want = D.CHAIN_PROBLEMS[index][seat]
        if row["problem"] != want:
            problems.append(f"{row['actor']}: problem {row['problem']} is not seat {seat} of chain {index}")
        want_tier = D.tier_of(want)
        if row.get("tier") != want_tier:
            problems.append(f"{row['actor']}: tier {row.get('tier')} does not match {want_tier}")
        if want_tier == "I" and want not in IMPOSSIBLE:
            problems.append(f"{row['actor']}: I-seat problem {want} is not in IMPOSSIBLE")
        if want_tier == "E" and want not in POSSIBLE:
            problems.append(f"{row['actor']}: E-seat problem {want} is not in POSSIBLE")
        if row.get("verifier") != verifier:
            problems.append(f"{row['actor']}: verifier is not {verifier}")
    return problems


def check(directory: Path) -> dict:
    protocol = read(directory / "protocol.json")
    task = SpilloverTask()
    problems = []
    live = task.prompts_record(integrity="plain", shared=False)["payload"]
    problems.extend(_prompt_problems(live, "prompts record"))
    if live.get("task") != TASK:
        problems.append("task text is not the spillover task")
    if TRANSMISSION_TASK.replace(CLAUSE_FROM, CLAUSE_TO) != TASK:
        problems.append("task text does not differ from transmission TASK only in the group clause")
    if CLAUSE_FROM in TASK or CLAUSE_TO not in TASK:
        problems.append("spillover TASK does not carry the group clause")
    if (directory / "prompts.json").exists():
        saved = read(directory / "prompts.json")
        payload = saved.get("payload") or saved
        problems.extend(_prompt_problems(payload, "saved prompts"))
        if payload.get("task") != TASK:
            problems.append("saved prompts task text is not the spillover task")
    tag = _protocol_verifier(protocol)
    planted = protocol.get("planted") or {}
    if tag == VERIFIER:
        if protocol.get("frozen", {}).get("verifier") != VERIFIER:
            problems.append(f"frozen verifier is not {VERIFIER}")
        if protocol.get("design_seed") != D.DESIGN_SEED:
            problems.append("design_seed is not the frozen T25 seed")
        if planted != planted_record():
            problems.append("protocol planted record does not match")
    elif tag != LEGACY_VERIFIER:
        problems.append(f"protocol verifier is not {VERIFIER}")
    if D.CHAIN_PROBLEMS[0] != ("double", "label_zero", "reverse_words", "clamp"):
        problems.append("c00 seat table does not match the preregistration")
    if D.CHAIN_PROBLEMS[1] != ("first_char", "choose_case", "unique_keep_order", "bracket_depth"):
        problems.append("c01 seat table does not match the preregistration")
    for index, names in D.CHAIN_PROBLEMS.items():
        for seat, name in enumerate(names):
            want = "I" if seat < 2 else "E"
            if D.tier_of(name) != want:
                problems.append(f"chain {index} seat {seat} tier is not {want}")
            if want == "I" and name not in IMPOSSIBLE:
                problems.append(f"{name} is marked I but is not in IMPOSSIBLE")
            if want == "E" and name not in POSSIBLE:
                problems.append(f"{name} is marked E but is not in POSSIBLE")

    schedule = read(directory / "schedule.json") if (directory / "schedule.json").exists() else []
    problems.extend(_seat_problems(schedule, tag))

    sessions = 0
    by_cell: dict[tuple[str, int], list[dict]] = {}
    for row in schedule:
        target = session_dir(directory, row["actor"])
        if not (target / "end.json").exists() and not (target / "meta" / "spec.json").exists():
            continue
        sessions += 1
        meta, actor = target / "meta", row["actor"]
        if (meta / "spec.json").exists():
            spec = read(meta / "spec.json")
            if spec.get("verifier") != tag:
                problems.append(f"{actor}: spec verifier is not {tag}")
            if spec.get("tier") != row.get("tier"):
                problems.append(f"{actor}: spec tier does not match the schedule")
            if spec.get("seat") != row.get("seat"):
                problems.append(f"{actor}: spec seat does not match the schedule")
        if not (target / "end.json").exists():
            continue
        if (meta / "opening.json").exists() and read(meta / "opening.json"):
            problems.append(f"{actor}: an opening message was sent")
        if (meta / "delivered.json").exists():
            delivered = read(meta / "delivered.json")
            try:
                want = extra_files(directory, row)
            except RuntimeError as exc:
                problems.append(f"{actor}: {exc}")
                continue
            got = {name: text.encode() for name, text in delivered.get("files", {}).items()}
            if got != want:
                problems.append(f"{actor}: delivered files differ from the carry-forward rule")
            if delivered.get("shared_sha256") and delivered["shared_sha256"] != shared_digest(got):
                problems.append(f"{actor}: recorded shared_sha256 does not match delivered files")
        by_cell.setdefault((row["chain"], row["generation"]), []).append(row)

    for (chain, generation), rows in sorted(by_cell.items()):
        hashes = []
        for row in rows:
            delivered_path = session_dir(directory, row["actor"]) / "meta" / "delivered.json"
            if delivered_path.exists():
                hashes.append(read(delivered_path).get("shared_sha256"))
        if hashes and len(set(hashes)) != 1:
            problems.append(f"{chain} g{generation:02d}: agents did not receive byte-identical shared/")
        merge_file = directory / "merges" / f"{chain}-g{generation:02d}.json"
        ended = [row for row in rows if (session_dir(directory, row["actor"]) / "end.json").exists()]
        if len(ended) != len(rows) or not ended:
            continue
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
        replay, _ = merge_record(received, agents, "all")
        stored = record_snapshot(directory, chain, generation)
        if stored != replay:
            problems.append(f"{chain} g{generation:02d}: stored record differs from replayed merge")
        if logged.get("record_files") != {name: sha256(data) for name, data in sorted(replay.items())}:
            problems.append(f"{chain} g{generation:02d}: merge log file list does not match the record")
        next_rows = [r for r in schedule if r["chain"] == chain and r["generation"] == generation + 1]
        if next_rows and (session_dir(directory, next_rows[0]["actor"]) / "end.json").exists():
            nxt = read(session_dir(directory, next_rows[0]["actor"]) / "meta" / "delivered.json")
            nxt_files = {name: text.encode() for name, text in nxt["files"].items()}
            if nxt_files != stored:
                problems.append(f"{chain} g{generation + 1:02d}: delivered record is not the previous merge")

    return {"sessions": sessions, "problems": problems, "ok": not problems}
