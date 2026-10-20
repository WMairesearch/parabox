"""Reconstruct descriptive resource tables from the shipped sanitized session rows."""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path


DEFAULT_DATA = Path(__file__).resolve().parents[1] / "report/resource-allocation"
TEXT_FIELDS = {
    "episode", "study", "model", "contributing_model", "condition", "task",
    "chain", "role", "source_row_sha256",
}
BOOLEAN_FIELDS = {
    "accepted", "published_violation", "saved_audit_violation", "audit_available",
    "argument_coverage_complete",
}
IDENTITY_FIELDS = TEXT_FIELDS | {"source_index", "generation", "turn_budget"}


def read_rows(raw):
    reader = csv.DictReader(io.StringIO(raw.decode("utf-8")))
    if not reader.fieldnames or len(set(reader.fieldnames)) != len(reader.fieldnames):
        raise ValueError("Unique CSV columns required")
    rows = []
    identities = set()
    for row in reader:
        if None in row or any(value is None for value in row.values()):
            raise ValueError("Malformed session row")
        for field, value in row.items():
            if field in TEXT_FIELDS:
                if not value or any(token in value for token in ("/", "\\", "\n")):
                    raise ValueError("Only path-free identifiers are allowed")
            elif value == "":
                row[field] = None
            elif field in BOOLEAN_FIELDS:
                if value not in {"true", "false"}:
                    raise ValueError("Boolean field must be true, false or empty")
                row[field] = value == "true"
            else:
                row[field] = int(value)
                if row[field] < 0:
                    raise ValueError("Counts cannot be negative")
        if row["episode"] in identities:
            raise ValueError("Duplicate session identity")
        identities.add(row["episode"])
        if not 0 <= row["turns_used"] <= row["turn_budget"]:
            raise ValueError("Invalid native turn count")
        checksum = row["source_row_sha256"]
        if len(checksum) != 64 or any(character not in "0123456789abcdef" for character in checksum):
            raise ValueError("Invalid source-row digest")
        rows.append(row)
    return rows


def load(directory):
    directory = Path(directory)
    provenance = json.loads((directory / "provenance.json").read_text())
    if provenance["schema_version"] != 1:
        raise ValueError("Unknown resource export schema")
    collections = {}
    for name in ("archived-sessions.csv", "peer-sessions.csv"):
        raw = (directory / name).read_bytes()
        manifest = provenance["exports"][name]
        if hashlib.sha256(raw).hexdigest() != manifest["sha256"]:
            raise ValueError(f"Export digest mismatch: {name}")
        rows = read_rows(raw)
        if len(rows) != manifest["sessions"]:
            raise ValueError(f"Session count mismatch: {name}")
        if list(csv.reader(io.StringIO(raw.decode())))[0] != manifest["columns"]:
            raise ValueError(f"Column mismatch: {name}")
        collections[name] = rows
    return collections, provenance


def aggregate(rows):
    metrics = {}
    for field in sorted(set().union(*(row.keys() for row in rows)) - IDENTITY_FIELDS):
        values = [row.get(field) for row in rows]
        known = [value for value in values if value is not None]
        result = {"known": len(known), "missing": len(values) - len(known)}
        if field in BOOLEAN_FIELDS:
            result.update(true=sum(value is True for value in known),
                          false=sum(value is False for value in known))
        elif known:
            result.update(total=sum(known), mean=round(sum(known) / len(known), 6))
        metrics[field] = result
    return {"sessions": len(rows), "independent_units": len({row["chain"] for row in rows}),
            "turn_budgets": sorted({row["turn_budget"] for row in rows}), "metrics": metrics}


def grouped(rows, fields):
    groups = defaultdict(list)
    for row in rows:
        groups[tuple(row[field] for field in fields)].append(row)
    return [{**dict(zip(fields, key, strict=True)), **aggregate(members)}
            for key, members in sorted(groups.items())]


def reconstruct(collections):
    archive = collections["archived-sessions.csv"]
    peers = collections["peer-sessions.csv"]
    windows = []
    for label, generations in (("first", {1}), ("late", {6, 7, 8})):
        for group in grouped([row for row in peers if row["generation"] in generations],
                             ("model", "contributing_model")):
            windows.append({"window": label, **group})
    return {
        "schema_version": 1,
        "archived": grouped(archive, ("study", "model", "condition")),
        "archived_generations": grouped(archive, ("study", "model", "condition", "generation")),
        "peer_generations": grouped(peers, ("model", "contributing_model", "generation")),
        "peer_windows": windows,
    }


def format_mean(group, field):
    value = group["metrics"][field].get("mean")
    return ("unknown" if value is None else
            str(Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)))


def report(summary, provenance):
    lines = [
        "# Resource allocation during method transmission", "",
        "Inherited methods change how agents spend actions on their own task, what the verifier accepts, "
        "and what they leave for successors. This report connects those observations without treating "
        "resource savings as legitimate success or additional work as harmful by definition.", "",
        "## Evidence and units", "",
        "The numeric export contains 992 archived sessions: 192 independent method-exposure sessions "
        "and 800 sessions nested in 100 eight-generation chains. A separate 720-session view follows "
        "three fixed recipients in each generation of 30 eight-generation peer-composition chains. "
        "The contributing model varies; the recipient model stays DeepSeek V4 Pro.", "",
        "All resource budgets here are native model turns. Means displayed to two decimals use half-up "
        "rounding. They are not the shared-wiki service's charged "
        "operation units, monetary costs, or successful operations. Command and submission dispatches "
        "count selected actions. Feature counts describe overlapping activity signatures, not intentions.", "",
        "## One encounter: expenditure and violating methods", "",
        "The exposure study uses contradictory functions, 16 sessions per condition and model, and "
        "a 24-turn ceiling. It measures shortcut susceptibility, not success on a genuinely solvable task.", "",
        "| Model | Condition | Sessions | Mean turns | Sessions with acceptance | Sessions with recorded violation |",
        "| --- | --- | ---: | ---: | ---: | ---: |",
    ]
    for group in summary["archived"]:
        if group["study"] != "method-exposure":
            continue
        metrics = group["metrics"]
        lines.append(f"| {group['model']} | {group['condition']} | {group['sessions']} | "
                     f"{format_mean(group, 'turns_used')} | {metrics['accepted']['true']} | "
                     f"{metrics['published_violation']['true']} |")
    lines += [
        "", "Exposure reduces average turns for every included model, but audited violations rise only "
        "for some. DeepSeek V4 Pro moves from 2 to 12 recorded violations while mean turns fall from "
        "23.63 to 16.69. Savings and misalignment are therefore distinct outcomes.", "",
        "## Eight generations: task outcomes and continued allocation", "",
        "Each condition below contains ten independent chains, eight generations, and a 50-turn ceiling. "
        "The code task has a successful reference implementation, while its original short-list convention "
        "is not fully stated to participants. Acceptance is the participant verifier's decision; "
        "recorded violations indicate accepted submissions that failed the saved independent audit.", "",
        "| Model | Condition | Sessions / chains | Mean turns | Sessions with acceptance | Sessions with recorded violation | Mean command dispatches | Mean submit dispatches |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for group in summary["archived"]:
        if group["study"] != "solvable-continuation":
            continue
        metrics = group["metrics"]
        lines.append(f"| {group['model']} | {group['condition']} | "
                     f"{group['sessions']} / {group['independent_units']} | {format_mean(group, 'turns_used')} | "
                     f"{metrics['accepted']['true']} | {metrics['published_violation']['true']} | "
                     f"{format_mean(group, 'command_dispatches')} | {format_mean(group, 'submit_dispatches')} |")
    lines += [
        "", "Three patterns coexist. DeepSeek V4 Pro's method condition combines fewer actions with more "
        "acceptance and violations. Gemini Flash improves acceptance and uses fewer turns without recorded "
        "violations. Kimi spends more turns while acceptance falls and violations appear. Resource accounting "
        "locates these different paths through the same task rather than collapsing them into a safety score.", "",
        "Within method-exposed chains, DeepSeek V4 Pro's mean falls from 31.1 turns in generation one to "
        "20.4 in generation eight; Gemini Flash moves from 50.0 to 21.0. These are descriptive trajectories "
        "within dependent chains. Carried material can include the original note: later recurrence is not "
        "automatically a newly authored transmission or an isolated causal effect of generation.", "",
        "## Fixed recipients: from task work to contributions", "",
        "The next table preserves the contributing-model comparison. Each setting has five independent "
        "chains; the first window contains 15 recipient sessions and the late window 45. Counts are "
        "summed dispatch signatures, except mean turns and the audit denominator. First-generation "
        "recipients have not yet received any generated peer outputs; differences in that first window "
        "are not responses to the contributing model's generated material.", "",
        "| Contributing model | Window | Sessions | Mean turns | Own writes | Verifier writes | Tests | Shared writes | Post-acceptance nonterminal actions | Violating sessions / sessions with known audits |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for group in summary["peer_windows"]:
        metrics = group["metrics"]
        values = [str(metrics[field].get("total", "unknown")) for field in (
            "own_artifact_writes", "verifier_surface_writes", "test_or_compile",
            "shared_writes", "post_acceptance_nonterminal_dispatches")]
        audit = metrics["saved_audit_violation"]
        lines.append(f"| {group['contributing_model']} | {group['window']} | {group['sessions']} | "
                     f"{format_mean(group, 'turns_used')} | " + " | ".join(values) +
                     f" | {audit['true']} / {audit['known']} |")
    lines += [
        "", "Under Flash and Qwen contributors, late recipients allocate more actions to their own "
        "implementation and fewer to the verifier surface than under the V4 Pro contributor. Verifier "
        "writes can include repairs or removal of a bypass; their direction is interpreted alongside "
        "the saved audits, not from the write count alone.", "",
        "Post-acceptance nonterminal actions show that activity continues after obtaining acceptance. "
        "Shared writes provide a route for later agents to encounter methods or corrections. These counts "
        "do not identify which advice was endorsed or used: those questions require the separate "
        "publication and lineage evidence. These allocations describe participation in shared work "
        "alongside own-task completion.", "",
        "## Provenance and reproduction", "",
        "The CSVs are allowlisted numeric projections of saved research censuses, not newly executed "
        "audits. They contain pseudonymous episode/chain IDs, original source-array indices and canonical "
        "source-row digests. Snapshot digests are retained in `provenance.json`; original snapshots and "
        "raw traces are not distributed here. Public reproduction verifies the shipped projections and "
        "reconstructs every aggregate, not the unavailable raw judgments.", "",
        "All 992 selected archived traces reconcile. One session has incomplete argument coverage; its "
        "argument-derived counts remain empty rather than zero. The peer view contains 19 sessions "
        "without accepted submissions; their saved audit flags remain null, not missing required audits "
        "or audit-clean successes. Published archive violation flags "
        "and peer audit flags retain their distinct definitions; they are never pooled.", "",
        "From the repository root:", "",
        "```sh", "python scripts/resource_report.py --check",
        "python scripts/resource_report.py --output-dir /tmp/resource-report", "```", "",
        "The check verifies CSV digests and regenerates `summary.json` and this report byte-for-byte. "
        "A fresh output directory receives regenerated aggregates and prose; existing outputs are not overwritten. "
        "No model, tool, or grader is executed.", "",
    ]
    return "\n".join(lines)


def artifacts(directory):
    collections, provenance = load(directory)
    summary = reconstruct(collections)
    sections = []
    for key, value in sorted(summary.items()):
        encoded = ("[\n" + ",\n".join("    " + json.dumps(row, sort_keys=True, allow_nan=False)
                                    for row in value) + "\n  ]"
                   if isinstance(value, list) else json.dumps(value))
        sections.append("  " + json.dumps(key) + ": " + encoded)
    return {"summary.json": "{\n" + ",\n".join(sections) + "\n}\n",
            "README.md": report(summary, provenance)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--check", action="store_true")
    action.add_argument("--output-dir", type=Path)
    args = parser.parse_args(argv)
    generated = artifacts(args.data_dir)
    if args.check:
        for name, text in generated.items():
            if (args.data_dir / name).read_text() != text:
                raise ValueError(f"Regeneration mismatch: {name}")
        print("Resource evidence and generated report verified; no experiments executed.")
    else:
        args.output_dir.mkdir(parents=True, exist_ok=False)
        for name, text in generated.items():
            (args.output_dir / name).write_text(text)


if __name__ == "__main__":
    main()
