"""python -m parabox.studies.unified prepare|run|audit|score|check|selftest|smoke"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="parabox.studies.unified")
    sub = parser.add_subparsers(dest="command", required=True)

    prep = sub.add_parser("prepare")
    prep.add_argument("directory", type=Path)
    prep.add_argument("--mode", choices=["single", "chain", "population"], required=True)
    prep.add_argument("--gate", choices=["harness", "state", "score", "open"], required=True)
    conditions = prep.add_mutually_exclusive_group(required=True)
    conditions.add_argument("--conditions", dest="arms", metavar="CONDITIONS",
                            help="comma-separated conditions; see docs/getting-started.md for names and aliases")
    conditions.add_argument("--arms", dest="arms", help=argparse.SUPPRESS)
    prep.add_argument("--problems", default=None, help="comma-separated problem keys")
    prep.add_argument("--model", required=True, help="model config path")
    prep.add_argument("--models", default=None, help="comma-separated configs for mixed arms")
    prep.add_argument("--lineages", type=int, default=4)
    prep.add_argument("--generations", type=int, default=None)
    prep.add_argument("--agents", type=int, default=4)
    prep.add_argument("--chains", type=int, default=2)
    prep.add_argument("--merge", choices=["all", "selected"], default="all")
    prep.add_argument("--turns", type=int, default=24)
    prep.add_argument("--seed", type=int, default=2026100901)
    prep.add_argument("--concurrency", type=int, default=8)
    prep.add_argument("--hard-stop", default=None, help="ISO timestamp with timezone, e.g. 2026-10-14T12:00:00Z")
    prep.add_argument("--reps", type=int, default=4)

    sub.add_parser("run").add_argument("directory", type=Path)
    rt = sub.add_parser("retry", help="move abnormal sessions aside, then run again")
    rt.add_argument("directory", type=Path)
    rt.add_argument("actors", nargs="*")
    sub.add_parser("audit").add_argument("directory", type=Path)
    sc = sub.add_parser("score")
    sc.add_argument("directory", type=Path)
    sc.add_argument("--out", type=Path, required=True)
    sub.add_parser("check").add_argument("directory", type=Path)
    sub.add_parser("selftest")
    sm = sub.add_parser("smoke")
    sm.add_argument("directory", type=Path)
    sm.add_argument("--gate", choices=["harness", "state", "score", "open"], required=True)
    sm.add_argument("--model", required=True)
    return parser


def _split(raw: str | None) -> list[str] | None:
    if not raw:
        return None
    return [item.strip() for item in raw.split(",") if item.strip()]


def dispatch(args) -> None:
    if args.command == "selftest":
        from parabox.studies.unified.selftest import selftest
        result = selftest()
        print(json.dumps({k: result[k] for k in ("ok", "problems")}, ensure_ascii=False, indent=2))
        raise SystemExit(0 if result["ok"] else 1)
    if args.command == "prepare":
        from parabox.studies.unified.run import prepare
        prepare(
            args.directory, mode=args.mode, gate=args.gate, arms=_split(args.arms),
            model_config=args.model, models=_split(args.models),
            lineages=args.lineages, generations=args.generations,
            agents=args.agents, chains=args.chains, merge=args.merge,
            turns=args.turns, seed=args.seed, concurrency=args.concurrency,
            hard_stop=args.hard_stop, reps=args.reps, problems=_split(args.problems),
        )
        print(f"prepared {args.directory}")
        return
    if args.command == "run":
        from parabox.studies.unified.run import run
        run(args.directory)
        return
    if args.command == "retry":
        from parabox.studies.unified.run import retry, run
        moved = retry(args.directory, args.actors)
        print(f"retrying {len(moved)} session(s)")
        if moved:
            run(args.directory)
        return
    if args.command == "audit":
        from parabox.studies.unified.run import audit
        print(json.dumps(audit(args.directory), ensure_ascii=False, indent=2))
        return
    if args.command == "score":
        from parabox.studies.unified.score import report
        print(json.dumps(report(args.directory, args.out), ensure_ascii=False, indent=2, default=str)[:2000])
        print(f"wrote {args.out}")
        return
    if args.command == "check":
        from parabox.studies.unified.check import check
        result = check(args.directory)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        raise SystemExit(0 if result["ok"] else 1)
    if args.command == "smoke":
        from parabox.studies.unified.run import smoke
        smoke(args.directory, gate=args.gate, model_config=args.model)
        return


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    try:
        dispatch(parser.parse_args(argv))
    except ValueError as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
