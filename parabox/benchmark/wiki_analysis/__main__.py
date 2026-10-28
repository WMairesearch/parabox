"""Export source evidence once; recompute portable measurements without model calls."""

import argparse
import json
from pathlib import Path

from .evidence import export
from .report import write


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    importing = commands.add_parser('export')
    importing.add_argument('--bundle', type=Path, required=True)
    importing.add_argument('--source-root', type=Path, required=True)
    importing.add_argument('--output', type=Path, required=True)
    analysis = commands.add_parser('analyze')
    analysis.add_argument('directory', type=Path)
    args = parser.parse_args()
    if args.command == 'export':
        export(args.bundle, args.source_root, args.output)
        result = write(args.output)
    else:
        result = write(args.directory)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
