"""Inspect saved execution evidence without running models, tools or graders."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .adapters import import_execution
from .io import read_bundle, write_bundle
from .query import select, summarize
from .schema import validate


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    incoming = commands.add_parser("import", help="Import a saved benchmark suite directory")
    incoming.add_argument("source", type=Path, help="Directory containing plan.json and execution/end.json")
    incoming.add_argument("--study", default="benchmark-execution")
    incoming.add_argument("--output", type=Path, required=True, help="New bundle file; never overwritten")
    for command in ("check", "summary", "query", "trace"):
        action = commands.add_parser(command)
        action.add_argument("bundle", type=Path)
        action.add_argument("--root", type=Path, required=True,
                            help="Source suite directory used to resolve and verify evidence paths")
        action.add_argument("--allow-external", action="store_true",
                            help="Explicitly permit bundle sources outside --root")
        action.add_argument("--structure-only", action="store_true",
                            help="Skip source verification; output is marked unverified")
        if command != "check":
            for field in ("kind", "model", "role", "run", "condition", "actor"):
                action.add_argument(f"--{field}")
            action.add_argument("--started", choices=["true", "false", "unknown"])
        if command in ("summary", "query"):
            action.add_argument("--measurement-prefix",
                                help="Keep matching measurements, for example resources. or task.")
        if command == "trace":
            action.add_argument("--id", help="Exact record ID when actor names are ambiguous")
    args = parser.parse_args(argv)
    if args.command == "import":
        bundle = import_execution(args.source, study=args.study)
        write_bundle(args.output, bundle)
        result = {"output": str(args.output), **validate(bundle),
                  "execution": "saved_evidence_only"}
    else:
        bundle = read_bundle(args.bundle, root=args.root,
                             verify_sources=not args.structure_only,
                             allow_external=args.allow_external)
        if args.command == "check":
            result = {**validate(bundle), "source_verified": not args.structure_only}
        else:
            records = select(bundle, **{field: getattr(args, field) for field in (
                "kind", "model", "role", "run", "condition", "actor", "started")})
            if args.command == "summary":
                payload = summarize(bundle, records=records)
                if args.measurement_prefix is not None:
                    for group in payload["groups"]:
                        group["measurements"] = [item for item in group["measurements"]
                                                 if item["name"].startswith(args.measurement_prefix)]
            elif args.command == "query":
                payload = []
                for record in records:
                    view = {key: value for key, value in record.items() if key != "events"}
                    if args.measurement_prefix is not None:
                        view["measurements"] = [item for item in record["measurements"]
                                                if item["name"].startswith(args.measurement_prefix)]
                    payload.append(view)
            else:
                if args.id:
                    records = [record for record in records if record["id"] == args.id]
                if len(records) != 1:
                    parser.error("trace requires exactly one record; qualify with --actor, --run or --id")
                record = records[0]
                payload = {"record": record, "relations": [
                    relation for relation in bundle["relations"]
                    if record["id"] in (relation["source"], relation["target"])],
                    "sources": bundle["sources"]}
            result = {"source_verified": not args.structure_only, "result": payload}
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
