"""python -m parabox.studies.continuation select|prepare|run|audit|report|selftest"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="parabox continuation")
    sub = parser.add_subparsers(dest="command", required=True)
    sel = sub.add_parser("select")
    sel.add_argument("source_run", type=Path, nargs="+")
    sel.add_argument("--out", type=Path, default=Path("report/continuation/selected.csv"))
    prep = sub.add_parser("prepare")
    prep.add_argument("source_run", type=Path)
    prep.add_argument("dest_run", type=Path)
    sub.add_parser("run").add_argument("directory", type=Path)
    sub.add_parser("audit").add_argument("directory", type=Path)
    sub.add_parser("report").add_argument("directory", type=Path)
    sub.add_parser("selftest")
    notes = sub.add_parser("review-notes")
    notes.add_argument("directory", type=Path)
    notes.add_argument("--out", type=Path, required=True)
    notes.add_argument("--cache", type=Path, default=None)
    return parser


def dispatch(args) -> None:
    from parabox.studies.continuation import run as R
    if args.command == "select":
        rows = []
        for source in args.source_run:
            rows.extend(R.select(source, args.out))
        print(f"wrote {args.out} ({len(rows)} rows this invocation)")
        return
    if args.command == "prepare":
        R.prepare(args.source_run, args.dest_run)
        return
    if args.command == "run":
        R.run(args.directory)
        return
    if args.command == "audit":
        print(json.dumps(R.audit(args.directory), ensure_ascii=False, indent=2))
        return
    if args.command == "report":
        print(json.dumps(R.report(args.directory), ensure_ascii=False, indent=2))
        return
    if args.command == "selftest":
        result = R.selftest()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        raise SystemExit(0 if result.get("ok") else 1)
    if args.command == "review-notes":
        from parabox.studies.continuation.notes import review_new_notes
        print(json.dumps(review_new_notes(args.directory, args.out, cache_dir=args.cache),
                         ensure_ascii=False, indent=2))


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    dispatch(parser.parse_args(argv))


if __name__ == "__main__":
    main()
