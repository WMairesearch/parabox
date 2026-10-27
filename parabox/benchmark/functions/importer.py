"""Offline projection of registered function runs into a portable evidence bundle."""

from __future__ import annotations

import json
from pathlib import Path

from parabox.benchmark.functions.design import PROFILES, build_plan, initial_files
from parabox.benchmark.protocol.config import default_spec
from parabox.benchmark.functions.evidence import session
from parabox.tasks.code.spec.transmission import TransmissionCodeTask
from parabox.util import read, save, sha256


def export(sources: list[dict], output: Path) -> dict:
    output = Path(output)
    if output.exists():
        raise ValueError("Evidence destination already exists")
    rows, protocols, seen, reconciliations = [], [], set(), []
    for source in sources:
        profile, model = source["profile"], source["model"]
        if (profile, model) in seen:
            raise ValueError("Duplicate profile/model source")
        seen.add((profile, model))
        root = Path(source["directory"])
        registration = read(root / "protocol.json")
        plan = read(root / "plan.json")["actors"]
        settings = PROFILES[profile]
        task = TransmissionCodeTask(50)
        prompts = task.prompts_record()
        if read(root / "prompts.json") != prompts:
            raise ValueError("Participant prompts differ from the installed function profile")
        mode = {"peer-composition": "population", "solvable-inheritance": "chain", "solvable-exposure": "single"}[profile]
        if (registration["mode"] != mode or registration["gate"] != "open"
                or registration["turns"] != 50 or registration["problems"] != ["second_item"]
                or registration["design_seed"] != settings["seed"]):
            raise ValueError("Registered task or schedule differs from profile")
        expected_count = settings["replicates"] * settings["generations"] * (
            settings["recipients"] + 1) * len(settings["conditions"])
        if len(plan) != expected_count:
            raise ValueError("Registered session count differs from profile")
        installed = build_plan(default_spec({model: "candidate.json"},
            "reference.json" if settings["recipients"] else None,
            "sha256:" + "0" * 64, function_profile=profile))["sessions"]
        original_order = [(
            "method" if row["arm"] == "mixed-method" else row["arm"],
            row["replicate"] - 1 if mode == "single" else row["chain_index"],
            row["generation"], row.get("agent") or 0) for row in plan]
        installed_order = [(row["condition"], row["replicate"], row["generation"], row["seat"])
                           for row in installed]
        if original_order != installed_order:
            raise ValueError("Registered assignments or order differ from installed profile")
        exported = []
        records = {row["actor"]: row for row in read(root / "records.json")}
        for assignment in plan:
            condition = "method" if assignment["arm"] == "mixed-method" else assignment["arm"]
            if condition not in settings["conditions"]:
                raise ValueError("Unexpected initial-record condition")
            initial = initial_files({"function_profile": profile, "condition": condition})
            if assignment["planted"] != {name: sha256(raw) for name, raw in initial.items()}:
                raise ValueError("Initial record bytes differ from installed seeds")
            actor = assignment["actor"]
            target = root / "sessions" / actor
            if read(target / "end.json").get("model") != assignment["model"]:
                raise ValueError("Executed model differs from registered participant")
            if settings["recipients"] and assignment["agent"] < settings["recipients"]:
                if assignment["model"] != "deepseek-v4-pro" or assignment["merge"] != "all":
                    raise ValueError("Fixed recipients or shared-file policy differ")
            workspace = target / "workspace"
            if (workspace / "PROBLEM.md").read_bytes() != task.workspace("second_item")["PROBLEM.md"]:
                raise ValueError("Problem wording differs from installed task")
            seat = assignment.get("agent") or 0
            chain = model + "-" + (assignment.get("chain") or actor)
            row = session(target, {"protocol": "function-" + profile, "chain": chain,
                "model": model, "condition": condition, "generation": assignment["generation"],
                "seat": seat, "seats": settings["recipients"] + 1,
                "role": "recipient" if seat < settings["recipients"] else "contributor",
                "problem": "second_item"})
            published = records[actor]
            if row["end"]["accepted"] != published["accepted"]:
                raise ValueError(f"Saved audit differs from published outcome: {profile}/{model}/{actor}")
            row["published_outcome"] = {"accepted": published["accepted"],
                                        "violation": published["cheat"], "audit_ok": published.get("audit_ok")}
            if (row["end"]["violation"] is True) != published["cheat"]:
                reconciliations.append({"id": row["id"], "published_violation": published["cheat"],
                                        "recomputed_violation": row["end"]["violation"],
                                        "audit": row["audit"]})
            row["source"]["actor"] = actor
            exported.append(row)
        rows.extend(exported)
        retries = list((root / "retried").rglob("end.json"))
        frozen = registration["frozen"]
        protocols.append({
            "profile": profile, "model": model, "protocol": "function-" + profile,
            "planned_sessions": expected_count, "exported_sessions": len(exported),
            "participants": sorted({row["participant_model"] for row in exported}),
            "original_image": frozen.get("image_id"),
            "prompt_sha256": prompts["sha256"],
            "problem_sha256": sha256(task.workspace("second_item")["PROBLEM.md"]),
            "source_hashes": {name: sha256((root / name).read_bytes()) for name in (
                "protocol.json", "plan.json", "prompts.json", "records.json")},
            "original_model_config_hashes": sorted(frozen["model_sha256"].values()),
            "model_configurations": sorted([
                {"model": participant, "template": "configs/" + Path(config).name,
                 "source_sha256": frozen["model_sha256"][config]}
                for participant, config in {(row["model"], row["model_config"]) for row in plan}
            ], key=lambda item: item["model"]),
            "retained_retry_ends": [sha256(path.read_bytes()) for path in sorted(retries)],
            "schedule": settings,
        })
    output.mkdir(parents=True)
    raw = "".join(json.dumps(row, sort_keys=True) + "\n" for row in sorted(rows, key=lambda row: row["id"]))
    (output / "sessions.jsonl").write_text(raw)
    save(output / "protocols.json", {
        "profiles": protocols,
        "participant_equivalence": "Prompt payload, initial-note bytes, problem wording, participant identities and assignment order checked against source runs.",
        "execution": "Installed runner uses a serial chain loop and explicit overall deadline; source runs used concurrent pipelines and study deadlines.",
        "audit_evidence": "Per-accepted-submission outcomes and original record digests; raw participant code and transcripts remain in source runs.",
        "reconciliations": reconciliations,
    })
    for profile in sorted({row["profile"] for row in protocols}):
        cohorts = [row for row in protocols if row["profile"] == profile]
        candidates = {}
        for cohort in cohorts:
            participant = next(row["participant_model"] for row in rows
                               if row["protocol"] == cohort["protocol"]
                               and row["model"] == cohort["model"] and row["role"] == "contributor")
            candidates[cohort["model"]] = next(binding["template"] for binding in
                cohort["model_configurations"] if binding["model"] == participant)
        reference = "configs/model-deepseek-v4-pro.json" if profile == "peer-composition" else None
        spec = default_spec(candidates, reference, "sha256:" + cohorts[0]["original_image"],
                            function_profile=profile)
        save(output / "specs" / (profile + ".json"), spec)
    manifest = {"schema": "parabox-evidence-v1", "sessions": len(rows), "planned_sessions": len(rows),
                "protocol_counts": {protocol: sum(row["protocol"] == protocol for row in rows)
                                    for protocol in sorted({row["protocol"] for row in rows})},
                "files": {str(path.relative_to(output)): sha256(path.read_bytes())
                          for path in sorted(output.rglob("*")) if path.is_file()}}
    save(output / "manifest.json", manifest)
    from parabox.benchmark.evaluation.analyze import analyze
    summary = analyze(output)
    save(output / "summary.json", summary)
    manifest["files"]["summary.json"] = sha256((output / "summary.json").read_bytes())
    save(output / "manifest.json", manifest)
    return {"sessions": len(rows), "protocol_counts": manifest["protocol_counts"]}
