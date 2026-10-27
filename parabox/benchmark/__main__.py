"""Offline preparation plus separately authorized execution."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from parabox.benchmark.protocol.config import default_spec, validate_spec
from parabox.benchmark.prepare import check, prepare


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(prog="python -m parabox.benchmark",
                                     description="Evaluate model influence on peers and shared practice maintenance.")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("selftest", help="Check installed assets and prepare offline")
    default = commands.add_parser("default-spec")
    default.add_argument("--candidate", action="append", required=True, metavar="NAME=CONFIG",
                         help="Contributor model in function populations; participant model in Wiki chains")
    default.add_argument("--reference", help="Fixed function recipients; omit for Wiki-only and single-agent function profiles")
    default.add_argument("--image", required=True, help="Immutable sha256:<image ID>")
    profiles = default.add_mutually_exclusive_group()
    profiles.add_argument("--historical", action="store_true",
                         help="Use the original founder-note withdrawal protocol")
    profiles.add_argument("--published", action="store_true",
                          help="Wiki only: six persistent positions, empty/artifacts/full, no reference population")
    from parabox.benchmark.functions.design import PROFILES
    profiles.add_argument("--function-profile", choices=tuple(PROFILES),
                          help="Run a published function configuration; peer-composition requires --reference")
    preparation = commands.add_parser("prepare")
    preparation.add_argument("directory", type=Path)
    preparation.add_argument("--spec", type=Path, required=True)
    checking = commands.add_parser("check")
    checking.add_argument("directory", type=Path)
    execution = commands.add_parser("run")
    execution.add_argument("directory", type=Path)
    execution.add_argument("--authorize-session-cap", type=int, required=True)
    execution.add_argument("--deadline", required=True)
    grading = commands.add_parser("grade", help="Audit saved sessions in independent containers")
    grading.add_argument("directory", type=Path)
    regrading = commands.add_parser("grade-evidence", help="Regrade published Wiki candidates in containers")
    regrading.add_argument("directory", type=Path)
    regrading.add_argument("--image", required=True)
    regrading.add_argument("--cache", type=Path, required=True)
    regrading.add_argument("--output", type=Path, required=True)
    analysis = commands.add_parser("analyze", help="Recompute descriptive results from saved evidence")
    analysis.add_argument("directory", type=Path)
    analysis.add_argument("--output", type=Path)
    exporting = commands.add_parser("export", help="Project executed ternary or graded function runs into a public evidence bundle")
    exporting.add_argument("directories", type=Path, nargs="+", metavar="RUN")
    exporting.add_argument("--output", type=Path, required=True)
    importing = commands.add_parser("import-functions", help="Project registered source runs into an offline evidence bundle")
    importing.add_argument("--sources", type=Path, required=True,
                           help="Private JSON list of profile, model and directory records")
    importing.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "selftest":
            from parabox.benchmark.protocol.selftest import selftest
            result = selftest()
        elif args.command == "default-spec":
            candidates = {}
            for entry in args.candidate:
                name, separator, path = entry.partition("=")
                if not separator or name in candidates:
                    raise ValueError("Expected unique NAME=CONFIG candidate declarations")
                candidates[name] = path
            result = validate_spec(default_spec(candidates, args.reference, args.image,
                                                historical=args.historical, published=args.published,
                                                function_profile=args.function_profile))
        elif args.command == "prepare":
            result = prepare(args.directory, json.loads(args.spec.read_text()))
        elif args.command == "check":
            result = check(args.directory)
        elif args.command == "analyze":
            from parabox.benchmark.evaluation.analyze import analyze
            result = analyze(args.directory)
            if args.output:
                args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
        elif args.command == "export":
            from parabox.benchmark.evaluation.export import export
            result = export(args.directories, args.output)
        elif args.command == "import-functions":
            from parabox.benchmark.functions.importer import export
            result = export(json.loads(args.sources.read_text()), args.output)
        elif args.command == "grade-evidence":
            from parabox.benchmark.evaluation.grade import grade_evidence
            result = grade_evidence(args.directory, image=args.image, cache=args.cache)
            args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
        elif args.command == "grade":
            from parabox.benchmark.evaluation.grade import grade
            result = grade(args.directory)
        else:
            from parabox.benchmark.run import run
            result = run(args.directory, authorize_session_cap=args.authorize_session_cap,
                         deadline=args.deadline)
    except (ValueError, OSError, KeyError, RuntimeError) as error:
        parser.error(str(error))
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
