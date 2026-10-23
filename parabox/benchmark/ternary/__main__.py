"""Command-line entry point for the ternary sequence experiment."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .run import check, prepare, run


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m parabox.benchmark.ternary")
    commands = parser.add_subparsers(dest="command", required=True)
    preparing = commands.add_parser("prepare")
    preparing.add_argument("directory", type=Path)
    preparing.add_argument("--spec", required=True, type=Path)
    checking = commands.add_parser("check")
    checking.add_argument("directory", type=Path)
    execution = commands.add_parser("run")
    execution.add_argument("directory", type=Path)
    execution.add_argument("--authorize-session-cap", type=int, required=True)
    execution.add_argument("--deadline", required=True)
    execution.add_argument("--workers", type=int, default=4)
    args = parser.parse_args(argv)
    try:
        if args.command == "prepare":
            result = prepare(args.directory, json.loads(args.spec.read_text()))
        elif args.command == "check":
            registration = check(args.directory)
            result = {"session_cap": registration["session_cap"], "chains": len(registration["chains"])}
        else:
            result = run(args.directory, authorize_session_cap=args.authorize_session_cap,
                         deadline=args.deadline, workers=args.workers)
    except (ValueError, OSError, KeyError, RuntimeError) as error:
        parser.error(str(error))
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
