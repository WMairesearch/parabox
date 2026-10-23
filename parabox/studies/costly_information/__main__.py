"""Command line interface for offline preparation and explicit execution."""
import argparse
import json
from pathlib import Path

from . import run


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    default = commands.add_parser("default-spec")
    default.add_argument("--model", action="append", required=True, metavar="NAME=CONFIG")
    default.add_argument("--image", required=True)
    default.add_argument("--scoring", choices=("final", "mean"), default="final")
    default.add_argument("--agents", type=int, choices=(1, 4), default=1)
    prepare = commands.add_parser("prepare")
    prepare.add_argument("--spec", type=Path, required=True)
    prepare.add_argument("--out", "--run-dir", dest="directory", type=Path, required=True)
    check = commands.add_parser("check")
    check.add_argument("--run-dir", "--out", dest="directory", type=Path, required=True)
    execute = commands.add_parser("run")
    execute.add_argument("--run-dir", "--out", dest="directory", type=Path, required=True)
    execute.add_argument("--authorize-session-cap", type=int, required=True)
    execute.add_argument("--deadline", required=True, help="Timezone-aware ISO 8601 host deadline")
    args = parser.parse_args(argv)
    if args.command == "default-spec":
        models = {}
        for value in args.model:
            name, separator, path = value.partition("=")
            if not separator or name in models:
                parser.error("Expected unique NAME=CONFIG entries")
            models[name] = path
        result = run.default_spec(models, args.image, args.scoring, args.agents)
    elif args.command == "prepare":
        result = run.prepare(args.spec, args.directory)
    elif args.command == "check":
        registration = run.checked(args.directory)
        result = {"registration_sha256": run.digest_json(registration), "session_cap": registration["session_cap"]}
    else:
        result = run.run(args.directory, args.authorize_session_cap, args.deadline)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
