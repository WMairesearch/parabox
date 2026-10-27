"""Standalone preparation, explicit execution, and saved-session grading."""
import argparse
import json
from pathlib import Path

from .design import default_spec, validate_spec, TRANSPORTS
from .prepare import prepare, check
from .run import run


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m parabox.studies.shared_wiki")
    commands = parser.add_subparsers(dest="command", required=True)
    default = commands.add_parser("default-spec")
    default.add_argument("--model", action="append", required=True, metavar="NAME=CONFIG")
    default.add_argument("--image", required=True, help="Immutable local sha256:<image ID>")
    default.add_argument("--transport", choices=TRANSPORTS, default="persistent")
    preparation = commands.add_parser("prepare", help="Bind sources and inputs offline")
    preparation.add_argument("directory", type=Path)
    preparation.add_argument("--spec", required=True, type=Path)
    checking = commands.add_parser("check")
    checking.add_argument("directory", type=Path)
    execution = commands.add_parser("run", help="Start explicitly authorized new sessions")
    execution.add_argument("directory", type=Path)
    execution.add_argument("--authorize-session-cap", required=True, type=int)
    execution.add_argument("--deadline", required=True)
    grading = commands.add_parser("grade", help="Grade saved sessions without model calls")
    grading.add_argument("directory", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "default-spec":
            models = {}
            for entry in args.model:
                name, separator, config = entry.partition("=")
                if not separator or name in models:
                    raise ValueError("Expected unique NAME=CONFIG declarations")
                models[name] = config
            result = validate_spec(default_spec(models, args.image, args.transport))
        elif args.command == "prepare":
            result = prepare(args.directory, json.loads(args.spec.read_text()))
        elif args.command == "check":
            result = check(args.directory)
        elif args.command == "grade":
            from .grade import grade
            result = grade(args.directory)
        else:
            result = run(args.directory, authorize_session_cap=args.authorize_session_cap, deadline=args.deadline)
    except (OSError, ValueError, KeyError, RuntimeError) as error:
        parser.error(str(error))
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
