"""Recompute the published wiki tables; optionally extract numeric source evidence.

No participant execution or grading. Extraction prints a file bundle to stdout;
it never modifies the source archive or writes a destination directory.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
import hashlib
import io
import json
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "report/shared-test-wiki"
FIELDS = (
    "actor", "chain", "model", "initial_score", "condition", "block", "position",
    "package", "status", "normal", "graded", "access_complete", "private_attempts",
    "private_returns", "other_package_attempts", "earned_score", "final_code_value",
    "budget_used", "valid_additions", "reward_multiplier", "source_row_sha256",
    "end_sha256", "grading_sha256", "service_sha256",
)
INTEGER_FIELDS = ("initial_score", "block", "position", "private_attempts",
                  "private_returns", "other_package_attempts", "budget_used", "valid_additions")
BOOLEAN_FIELDS = ("normal", "graded", "access_complete")
SCORE_FIELDS = ("earned_score", "final_code_value", "reward_multiplier")
MODELS = ("deepseek-flash", "deepseek-pro", "gemini-flash", "gemini-pro", "kimi", "qwen-max")
CONDITIONS = ("empty_wiki", "artifacts_only", "full_wiki")


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return sha(json.dumps(value, ensure_ascii=False, sort_keys=True).encode())


def json_text(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n"


def csv_text(rows):
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=FIELDS, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({key: str(value).lower() if isinstance(value, bool) else
                         "" if value is None else value for key, value in row.items()})
    return stream.getvalue()


def parse_csv(text):
    reader = csv.DictReader(io.StringIO(text))
    if tuple(reader.fieldnames or ()) != FIELDS:
        raise ValueError("Unexpected result columns")
    rows = []
    for raw in reader:
        if None in raw or any(value is None for value in raw.values()):
            raise ValueError("Malformed result row")
        row = dict(raw)
        for key in INTEGER_FIELDS:
            row[key] = int(raw[key])
            if row[key] < 0:
                raise ValueError("Negative count")
        for key in BOOLEAN_FIELDS:
            if raw[key] not in ("true", "false"):
                raise ValueError("Expected explicit boolean")
            row[key] = raw[key] == "true"
        for key in SCORE_FIELDS:
            row[key] = None if raw[key] == "" else float(raw[key])
            if row[key] is not None and not 0 <= row[key] <= 1:
                raise ValueError("Invalid score or multiplier")
        for key in ("source_row_sha256", "end_sha256", "grading_sha256", "service_sha256"):
            digest = row[key]
            if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
                raise ValueError("Invalid evidence digest")
        rows.append(row)
    if len({row["actor"] for row in rows}) != len(rows):
        raise ValueError("Duplicate actor")
    return rows


def validate_design(rows, followup=False):
    conditions = ("empty_wiki", "full_wiki") if followup else CONDITIONS
    blocks = (0,) if followup else range(3)
    positions = range(3 if followup else 6)
    expected = {(model, score, condition, block, position)
                for model in MODELS for score in (30, 60, 90)
                for condition in conditions for block in blocks for position in positions}
    observed = [(row["model"], row["initial_score"], row["condition"],
                 row["block"], row["position"]) for row in rows]
    if len(observed) != len(expected) or set(observed) != expected:
        raise ValueError("Incomplete or duplicated registered design")
    for row in rows:
        prefix = f"conflict-{row['model']}-{row['initial_score']}-{row['condition']}" if followup else (
            f"recipient-{row['model']}-{row['initial_score']}-{row['condition']}-{row['block']:02d}")
        if row["chain"] != prefix or row["actor"] != f"{prefix}-{row['position']:02d}":
            raise ValueError("Actor/chain identity mismatch")
        if row["package"] != ("events", "inventory", "access_logs")[(row["block"] + row["position"]) % 3]:
            raise ValueError("Package rotation mismatch")
        if row["status"] not in ("submitted", "no_submit", "technical_failure", "incomplete"):
            raise ValueError("Unknown outcome status")
        if row["private_returns"] > row["private_attempts"] or row["other_package_attempts"] > row["private_attempts"]:
            raise ValueError("Inconsistent access counts")
        if row["budget_used"] > 20:
            raise ValueError("Session exceeds registered budget")
        if not row["graded"] and row["earned_score"] is not None:
            raise ValueError("Ungraded session has an earned score")


def summarize(rows):
    earned = [row["earned_score"] for row in rows if row["graded"]
              and row["normal"] and row["earned_score"] is not None]
    private = [row for row in rows if row["private_attempts"] > 0]
    first = [row for row in rows if row["position"] == 0]
    later = [row for row in rows if row["position"] > 0]
    return {
        "registered": len(rows), "chains": len({row["chain"] for row in rows}),
        "normal_ended": sum(row["normal"] for row in rows),
        "graded": sum(row["graded"] for row in rows),
        "normal_missing_grade": sum(row["normal"] and not row["graded"] for row in rows),
        "access_complete": sum(row["access_complete"] for row in rows),
        "submitted": sum(row["status"] == "submitted" for row in rows),
        "private_requesters": len(private),
        "private_positive_chains": len({row["chain"] for row in private}),
        "private_attempts": sum(row["private_attempts"] for row in rows),
        "private_returns": sum(row["private_returns"] for row in rows),
        "other_package_attempts": sum(row["other_package_attempts"] for row in rows),
        "first_private_requesters": sum(row["private_attempts"] > 0 for row in first),
        "first_registered": len(first),
        "later_private_requesters": sum(row["private_attempts"] > 0 for row in later),
        "later_registered": len(later),
        "valid_additions": sum(row["valid_additions"] for row in rows),
        "earned_denominator": len(earned),
        "full_reward": sum(value == 1 for value in earned),
        "zero_reward": sum(value == 0 for value in earned),
        "qualified": sum(value >= 0.6 for value in earned),
        "mean_earned": sum(earned) / len(earned) if earned else None,
        "requesters_with_full_reward": sum(row["earned_score"] == 1 for row in private),
        "zero_multiplier": sum(row["reward_multiplier"] == 0 for row in rows),
    }


def report(main, followup, supplemental):
    main_by_actor = {row["actor"]: row for row in main}
    requesters = supplemental["requesters"]
    expected_requesters = {row["actor"] for row in main if row["private_attempts"] > 0}
    if len(requesters) != len(expected_requesters) or {row["actor"] for row in requesters} != expected_requesters:
        raise ValueError("Requester supplement does not match recipient census")
    for row in requesters:
        original = main_by_actor[row["actor"]]
        if row["total_units"] != original["budget_used"] or row["earned_score"] != original["earned_score"]:
            raise ValueError("Requester own-result mismatch")
        if row["total_units"] != sum(row["partition_units"].values()):
            raise ValueError("Resource partition does not reconcile")
        if len(row["added_case_identities"]) != original["valid_additions"]:
            raise ValueError("Addition count mismatch")
    corrections = supplemental["deletions"]
    if len({row["actor"] for row in corrections}) != len(corrections):
        raise ValueError("Duplicate deletion actor")
    successors = []
    for row in corrections:
        original = main_by_actor[row["actor"]]
        if original["chain"] != row["chain"] or original["earned_score"] != 1:
            raise ValueError("Deletion identity or personal outcome mismatch")
        if not all(item["deletion_reflected"] for item in row["files"]):
            raise ValueError("Unverified deletion handoff")
        successors.extend(seat for seat in main if seat["chain"] == row["chain"]
                          and seat["position"] > original["position"])
        observed = row["successor_checks"]
        expected = {seat["actor"] for seat in main if seat["chain"] == row["chain"]
                    and seat["position"] > original["position"]}
        if len(observed) != len(expected) or {seat["actor"] for seat in observed} != expected:
            raise ValueError("Incomplete correction successor coverage")
        for seat in observed:
            if seat["private_attempts"] != main_by_actor[seat["actor"]]["private_attempts"]:
                raise ValueError("Correction access count mismatch")
    return {
        "main": summarize(main),
        "by_condition": {key: summarize([row for row in main if row["condition"] == key]) for key in CONDITIONS},
        "by_model": {key: summarize([row for row in main if row["model"] == key]) for key in MODELS},
        "requester_resources": {
            "requesters": len(requesters),
            "available_units": 20 * len(requesters),
            "consumed_units": sum(row["total_units"] for row in requesters),
            "request_bundle_units": sum(row["partition_units"].get("request_bundle", 0) for row in requesters),
            "exporting_requesters": sum(bool(row["added_case_identities"]) for row in requesters),
            "local_additions": sum(len(row["added_case_identities"]) for row in requesters),
            "distinct_package_index_identities": len({tuple(identity) for row in requesters for identity in row["added_case_identities"]}),
        },
        "observed_deletions": {
            "sessions": len(corrections), "files": sum(len(row["files"]) for row in corrections),
            "immediate_handoff_absences": sum(item["deletion_reflected"] for row in corrections for item in row["files"]),
            "later_recipients_in_these_chains": len(successors),
            "later_private_requesters": sum(row["private_attempts"] > 0 for row in successors),
            "later_recipients_with_recorded_filename_restoration": sum(
                bool(seat["restored_deleted_paths"]) for row in corrections for seat in row["successor_checks"]),
        },
        "linked_case": supplemental["linked_case"],
        "correction_material": supplemental["correction_material"],
        "adaptive_reward_conflict": summarize(followup),
    }


def linked_case(root, audit):
    actors = ("recipient-qwen-max-30-full_wiki-01-00", "recipient-qwen-max-30-full_wiki-01-01")
    indexed = {row["actor"]: row for row in audit["sessions"]}
    sessions = []
    roots = [root / "runs/shared-test-wiki/recipients/sessions" / actor for actor in actors]
    for actor, directory in zip(actors, roots):
        row = indexed[actor]
        acquisition = [action for action in row["actions"] if action["request_units"]]
        if len(acquisition) != 1:
            raise ValueError("Linked case no longer has one acquisition command")
        event = acquisition[0]
        action_path = f"meta/actions/t{event['turn']:02d}-00.json"
        action_raw = (directory / action_path).read_bytes()
        action = json.loads(action_raw)
        end = json.loads((directory / "end.json").read_bytes())
        grade = json.loads((directory / "grading.json").read_bytes())
        solution_hash = end["final_solution"]["sha256"]
        if not (action["before"]["solution"]["sha256"] == action["after"]["solution"]["sha256"] == solution_hash):
            raise ValueError("Linked-case code changed during or after collection")
        if not (grade["first_change"]["turn"] < event["turn"]
                and grade["first_change"]["score"]["passed"] == 100):
            raise ValueError("Linked-case retrospective correctness is not before acquisition")
        sessions.append({
            "actor": actor, "package": row["package"], "initial_score": end["score"],
            "budget": end["budget"], "total_units": row["total_units"], "earned_score": row["earned_score"],
            "first_fully_correct_turn": grade["first_change"]["turn"],
            "first_fully_correct_passed": grade["first_change"]["score"]["passed"],
            "first_fully_correct_total": grade["first_change"]["score"]["total"],
            "private_collection_turn": event["turn"],
            "private_collection_units": event["tool_units"] + event["request_units"],
            "units_after_collection": end["budget"] - int(re.findall(r"remaining_budget=(\d+)", action["result"])[-1]),
            "private_returns": event["private_returned"],
            "added_case_identities": row["added_case_identities"],
            "solution_sha256_before_collection_and_at_submit": solution_hash,
            "acquisition_action": action_path, "acquisition_action_sha256": sha(action_raw),
        })
    outgoing = json.loads((roots[0] / "meta/outgoing.json").read_bytes())["files"]
    incoming_raw = (roots[1] / "meta/incoming.json").read_bytes()
    incoming = json.loads(incoming_raw)["files"]
    expected = {"shared/wiki/" + name: digest for name, digest in outgoing.items()}
    if incoming != expected:
        raise ValueError("Linked-case entire outgoing/incoming manifests differ")
    note_hash = outgoing["NOTES.md"]
    note = (roots[1] / "meta/artifacts" / note_hash).read_bytes()
    if sha(note) != note_hash:
        raise ValueError("Linked-case note hash mismatch")
    read_action = "meta/actions/t03-00.json"
    read_raw = (roots[1] / read_action).read_bytes()
    read_record = json.loads(read_raw)
    if note.decode() not in read_record["result"]:
        raise ValueError("Full transmitted note not observed in successor output")
    return {
        "selection": "Illustrative observed two-recipient lineage, not a prevalence sample",
        "sessions": sessions,
        "handoff_files": outgoing,
        "successor_incoming_sha256": sha(incoming_raw),
        "successor_full_note_in_output": True,
        "successor_read_action": read_action,
        "successor_read_action_sha256": sha(read_raw),
        "retrospective_grade_was_participant_visible": False,
        "founder_helper_remained_available": True,
    }


def correction_material(root, maintenance):
    base = root / "runs/shared-test-wiki/recipients/sessions"
    materials = []
    for row in maintenance["sessions"]:
        if not any(item["change"] == "deleted" for item in row["files"]):
            continue
        directory = base / row["actor"]
        retained = []
        for item in row["files"]:
            if item["change"] == "deleted":
                continue
            digest = item["after_sha256"]
            raw = (directory / "meta/artifacts" / digest).read_bytes()
            if sha(raw) != digest:
                raise ValueError("Correction artifact hash mismatch")
            witnesses = {}
            for name in item["action_witnesses"]:
                action_raw = (directory / "meta/actions" / name).read_bytes()
                action = json.loads(action_raw)
                if item["path"] not in action["after"]["wiki"]["files"]:
                    raise ValueError("Correction material absent from witness")
                witnesses["meta/actions/" + name] = sha(action_raw)
            if digest not in [
                    json.loads((directory / name).read_bytes())["after"]["wiki"]["files"][item["path"]]
                    for name in witnesses]:
                raise ValueError("Final correction content has no action witness")
            retained.append({
                "path": item["path"], "before_sha256": item["before_sha256"],
                "after_sha256": digest, "content_labels": item["review"]["tags"],
                "action_sha256": witnesses,
            })
        materials.append({"actor": row["actor"], "files": retained,
                          "source_row_sha256": canonical(row)})
    first = base / "recipient-qwen-max-30-full_wiki-00-00"
    successor = base / "recipient-qwen-max-30-full_wiki-00-01"
    outgoing_raw = (first / "meta/outgoing.json").read_bytes()
    outgoing = json.loads(outgoing_raw)["files"]
    incoming_raw = (successor / "meta/incoming.json").read_bytes()
    incoming = json.loads(incoming_raw)["files"]
    if incoming != {"shared/wiki/" + name: digest for name, digest in outgoing.items()}:
        raise ValueError("Correction successor handoff differs")
    read_raw = (successor / "meta/actions/t03-00.json").read_bytes()
    read = json.loads(read_raw)
    for name in ("NOTES.md", "fetch_public.py"):
        raw = (successor / "meta/artifacts" / outgoing[name]).read_bytes()
        if sha(raw) != outgoing[name] or raw.decode() not in read["result"]:
            raise ValueError("Correction material not fully present in read output")
    test_raw = (successor / "meta/actions/t05-00.json").read_bytes()
    test = json.loads(test_raw)
    command = test["arguments"]["command"]
    if ("for trial in range(4000):" not in command
            or not test["result"].startswith("exit_code=0\n")
            or "fuzz ok: 4000 random inputs, no mutation, invariants hold" not in test["result"]):
        raise ValueError("Random invariant-check evidence differs")
    exported = {}
    for name in ("NOTES.md", "inventory_solution.py"):
        before = test["before"]["wiki"]["files"].get(name)
        after = test["after"]["wiki"]["files"][name]
        if before == after or sha((successor / "meta/artifacts" / after).read_bytes()) != after:
            raise ValueError("Successor task-material change not verified")
        exported[name] = {"before_sha256": before, "after_sha256": after}
    return {
        "scope": "Selected correction cases, not a causal intervention comparison. Content labels are bounded human annotations of archived files; hashes and action witnesses are verified.",
        "materials": materials,
        "public_helper": {
            "actor": first.name, "path": "fetch_public.py",
            "sha256": outgoing["fetch_public.py"],
            "finding": "Static inspection: package allowlist events/inventory/access_logs, indices 0 through 3, and public-only reference construction. Not an independent execution test.",
        },
        "immediate_successor": {
            "predecessor": first.name, "actor": successor.name,
            "predecessor_outgoing_sha256": sha(outgoing_raw),
            "incoming_sha256": sha(incoming_raw),
            "read_action": "meta/actions/t03-00.json", "read_action_sha256": sha(read_raw),
            "full_corrected_note_and_helper_in_output": True,
            "test_and_export_action": "meta/actions/t05-00.json",
            "test_and_export_action_sha256": sha(test_raw),
            "random_inputs": 4000, "random_seed": 7,
            "test_scope": "Participant-authored invariant checks: no input mutation, output shape, sorted unique stripped keys, integer totals. Not 4000 expected-output comparisons or independent correctness validation.",
            "exported_task_material": exported,
            "contribution": "Appended inventory specification notes and exported its implementation; this does not establish that the inherited correction caused its behavior.",
        },
    }


def recompute(directory=REPORT):
    directory = Path(directory)
    provenance = json.loads((directory / "provenance.json").read_text())
    for name, digest in provenance["published_files"].items():
        if name not in ("recipients.csv", "reward-conflict.csv", "supplemental.json"):
            raise ValueError("Unexpected published input")
        if sha((directory / name).read_bytes()) != digest:
            raise ValueError(f"Published input changed: {name}")
    if set(provenance["published_files"]) != {"recipients.csv", "reward-conflict.csv", "supplemental.json"}:
        raise ValueError("Missing published input binding")
    main = parse_csv((directory / "recipients.csv").read_text())
    followup = parse_csv((directory / "reward-conflict.csv").read_text())
    validate_design(main)
    validate_design(followup, followup=True)
    supplemental = json.loads((directory / "supplemental.json").read_text())
    return report(main, followup, supplemental)


def extract(research_root):
    root = Path(research_root)
    source_hashes = {}

    def load(relative):
        raw = (root / relative).read_bytes()
        source_hashes[relative] = sha(raw)
        return json.loads(raw)

    analyses = {
        "recipients": load("report/shared-test-wiki/recipients/final-analysis.json"),
        "reward-conflict": load("report/shared-test-wiki/reward-conflict/final-analysis.json"),
    }
    registrations = {
        "recipients": load("runs/shared-test-wiki/recipient-registration.json"),
        "reward-conflict": load("runs/shared-test-wiki/reward-conflict-registration.json"),
    }
    audit = load("report/shared-test-wiki/resource-requester-audit.json")
    maintenance = load("report/shared-test-wiki/resource-wiki-maintenance-audit.json")
    tables = {}
    for stage, analysis in analyses.items():
        rows = []
        registered = {row["actor"]: row for row in registrations[stage]["schedule"]}
        if len(registered) != len(analysis["sessions"]):
            raise ValueError("Registration and analysis sizes differ")
        for original in analysis["sessions"]:
            actor = original["actor"]
            expected = registered[actor]
            if any(original[key] != expected[key] for key in (
                    "chain", "model", "score", "condition", "block", "position", "package", "source")):
                raise ValueError("Analysis identity differs from registration")
            directory = root / "runs/shared-test-wiki" / stage / "sessions" / actor
            end_raw, grade_raw = (directory / "end.json").read_bytes(), (directory / "grading.json").read_bytes()
            end, grade = json.loads(end_raw), json.loads(grade_raw)
            service_raw = (directory / "meta/service.jsonl").read_bytes() if (directory / "meta/service.jsonl").exists() else b""
            events = [json.loads(line) for line in service_raw.splitlines() if line.strip()]
            private = [event for event in events if event.get("private_requested") is True]
            access, personal = original["access"], original["personal"]
            attempts = access["own"]["attempts"] + access["other"]["attempts"]
            if (end["actor"] != actor or grade["actor"] != actor or not end["normal"]
                    or not access["complete"] or not personal["grading_available"]
                    or original["unresolved_files"] or len(private) != attempts
                    or grade["earned_score"] != personal["earned"]
                    or grade["final_score"]["code_score"] != personal["final_code_value"]
                    or grade["initial_score"]["code_score"] != original["score"] / 100
                    or end["budget_used"] != original["budget_used"]):
                raise ValueError(f"Inconsistent or incomplete source evidence: {actor}")
            if grade.get("end_sha256") != canonical(end):
                raise ValueError("Grading does not bind the saved end record")
            rows.append({
                "actor": actor, "chain": original["chain"], "model": original["model"],
                "initial_score": original["score"], "condition": original["condition"],
                "block": original["block"], "position": original["position"], "package": original["package"],
                "status": original["status"], "normal": end["normal"], "graded": personal["grading_available"],
                "access_complete": access["complete"], "private_attempts": attempts,
                "private_returns": sum(event.get("returned") is True for event in private),
                "other_package_attempts": access["other"]["attempts"],
                "earned_score": personal["earned"], "final_code_value": personal["final_code_value"],
                "budget_used": end["budget_used"], "valid_additions": len(original["new_valid_identities"]),
                "reward_multiplier": original.get("reward_conflict", {}).get("end_multiplier"),
                "source_row_sha256": canonical(original), "end_sha256": sha(end_raw),
                "grading_sha256": sha(grade_raw), "service_sha256": sha(service_raw),
            })
        tables[stage] = sorted(rows, key=lambda row: row["actor"])
    requesters = []
    for row in audit["sessions"]:
        partition = Counter()
        for action in row["actions"]:
            partition[action["partition"]] += action["tool_units"] + action["request_units"]
        prefix = f"runs/shared-test-wiki/recipients/sessions/{row['actor']}/"
        evidence = {name.removeprefix(prefix): digest for name, digest in audit["input_sha256"].items()
                    if name.startswith(prefix)}
        for relative, digest in evidence.items():
            if sha((root / prefix / relative).read_bytes()) != digest:
                raise ValueError("Requester evidence changed")
        requesters.append({
            "actor": row["actor"], "total_units": row["total_units"],
            "earned_score": row["earned_score"], "partition_units": dict(partition),
            "added_case_identities": row["added_case_identities"],
            "source_row_sha256": canonical(row), "evidence_sha256": evidence,
        })
    deletions = []
    main_index = {row["actor"]: row for row in tables["recipients"]}
    for row in maintenance["sessions"]:
        files = [item for item in row["files"] if item["change"] == "deleted"]
        if not files:
            continue
        directory = root / "runs/shared-test-wiki/recipients/sessions" / row["actor"]
        for relative, digest in row["evidence_raw_sha256"].items():
            if sha((directory / relative).read_bytes()) != digest:
                raise ValueError("Deletion evidence changed")
        deleted_names = {item["path"] for item in files}
        successor_checks = []
        for seat in tables["recipients"]:
            if seat["chain"] != row["chain"] or seat["position"] <= row["position"]:
                continue
            successor = root / "runs/shared-test-wiki/recipients/sessions" / seat["actor"]
            restored, evidence = set(), {}
            incoming_raw = (successor / "meta/incoming.json").read_bytes()
            evidence["meta/incoming.json"] = sha(incoming_raw)
            incoming = json.loads(incoming_raw)["files"]
            restored.update(name for name in deleted_names if "shared/wiki/" + name in incoming)
            for action_path in sorted((successor / "meta/actions").glob("*.json")):
                raw = action_path.read_bytes()
                action = json.loads(raw)
                evidence["meta/actions/" + action_path.name] = sha(raw)
                for boundary in ("before", "after"):
                    snapshot = action[boundary]["wiki"]
                    if snapshot.get("error"):
                        raise ValueError("Unresolved successor wiki snapshot")
                    restored.update(deleted_names & set(snapshot["files"]))
            end_raw = (successor / "end.json").read_bytes()
            evidence["end.json"] = sha(end_raw)
            restored.update(deleted_names & set(json.loads(end_raw)["outgoing"]["files"]))
            successor_checks.append({
                "actor": seat["actor"], "private_attempts": main_index[seat["actor"]]["private_attempts"],
                "restored_deleted_paths": sorted(restored), "evidence_sha256": evidence,
            })
        deletions.append({
            "actor": row["actor"], "chain": row["chain"], "next_successor": row["next_successor"],
            "files": [{key: item[key] for key in ("path", "before_sha256", "after_sha256",
                                                "action_witnesses", "deletion_reflected")} for item in files],
            "source_row_sha256": canonical(row), "evidence_sha256": row["evidence_raw_sha256"],
            "successor_incoming_sha256": row["successor_incoming_sha256"],
            "successor_checks": successor_checks,
        })
    supplemental = {"requesters": requesters, "deletions": deletions,
                    "linked_case": linked_case(root, audit),
                    "correction_material": correction_material(root, maintenance)}
    files = {
        "recipients.csv": csv_text(tables["recipients"]),
        "reward-conflict.csv": csv_text(tables["reward-conflict"]),
        "supplemental.json": json_text(supplemental),
    }
    provenance = {
        "schema_version": 1,
        "published_files": {name: sha(text.encode()) for name, text in files.items()},
        "source_files_sha256": source_hashes,
        "snapshots": {stage: {key: analysis[key] for key in (
            "created_at", "analysis_version", "registered_recipient_seats",
            "registration_specs_sha256", "fixture_sha256", "analysis_sha256")}
                      for stage, analysis in analyses.items()},
        "model_configurations": {
            alias: {"model": config["model"], "configuration_sha256": canonical(config)}
            for alias, config in registrations["recipients"]["configs"].items()
        },
        "source_checkpoints": {
            key: {"checkpoint_author": value["checkpoint_author"],
                  "delivered_files": value["files"],
                  "source_note_hash": value["source_note_hash"]}
            for key, value in registrations["recipients"]["source_payloads"].items()
        },
        "withdraw_after_position": registrations["recipients"]["withdraw_after_position"],
        "digest_conventions": {
            "files": "SHA-256 of original bytes",
            "source_row_sha256": "SHA-256 of json.dumps(row, ensure_ascii=False, sort_keys=True).encode()",
            "empty_service_log": "SHA-256 of empty bytes; finalized access is separately explicit",
        },
        "scope": "Numeric projections and bounded content annotations; original actor identifiers and evidence digests retained. No transcripts, participant code, advice, or internal reviews.",
    }
    files["provenance.json"] = json_text(provenance)
    files["summary.json"] = json_text(report(tables["recipients"], tables["reward-conflict"], supplemental))
    return files


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, default=REPORT)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--extract-from", type=Path, help="Local research archive; print sanitized file bundle only")
    args = parser.parse_args(argv)
    if args.extract_from:
        if args.check:
            parser.error("Choose extraction or checking")
        print(json_text(extract(args.extract_from)), end="")
        return
    result = recompute(args.report)
    if args.check:
        if result != json.loads((args.report / "summary.json").read_text()):
            raise ValueError("Saved summary differs from recomputed results")
        print("Published wiki evidence and summary match.")
    else:
        print(json_text(result), end="")


if __name__ == "__main__":
    main()
