"""Checkout-only commands for historical study runners."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python -m parabox.studies.cli",
        description="Historical study commands requiring a source checkout and study-specific inputs.",
    )
    sub = parser.add_subparsers(dest="group", required=True)
    lean = sub.add_parser("lean").add_subparsers(dest="command", required=True)
    lean.add_parser("selftest")
    relay = sub.add_parser("relay").add_subparsers(dest="command", required=True)
    prep = relay.add_parser("prepare")
    prep.add_argument("directory", type=Path)
    prep.add_argument("--blocks", type=int, default=12)
    prep.add_argument("--generations", type=int, default=5)
    prep.add_argument("--integrity", choices=["library", "paper"], default="library")
    for name in ("run", "audit", "check", "review", "report"):
        relay.add_parser(name).add_argument("directory", type=Path)
    again = relay.add_parser("retry")
    again.add_argument("directory", type=Path)
    again.add_argument("actors", nargs="+")
    rb = sub.add_parser("relayboard").add_subparsers(dest="command", required=True)
    rb_prep = rb.add_parser("prepare")
    rb_prep.add_argument("directory", type=Path)
    rb_prep.add_argument("--blocks", type=int, default=12)
    rb_prep.add_argument("--generations", type=int, default=5)
    rb_prep.add_argument("--integrity", choices=["library", "paper"], default="library")
    rb_prep.add_argument("--style", choices=["described", "minimal"], default="described")
    rb_prep.add_argument("--isolated-from", type=Path, default=None)
    for name in ("run", "audit", "check", "review", "report"):
        rb.add_parser(name).add_argument("directory", type=Path)
    rb_compare = rb.add_parser("compare")
    rb_compare.add_argument("directory", type=Path)
    rb_compare.add_argument("other", type=Path)
    rb_retry = rb.add_parser("retry")
    rb_retry.add_argument("directory", type=Path)
    rb_retry.add_argument("actors", nargs="+")

    rf = sub.add_parser("relayfiles").add_subparsers(dest="command", required=True)
    rf_prep = rf.add_parser("prepare")
    rf_prep.add_argument("directory", type=Path)
    rf_prep.add_argument("--blocks", type=int, default=12)
    rf_prep.add_argument("--generations", type=int, default=5)
    rf_prep.add_argument("--integrity", choices=["library", "paper"], default="library")
    rf_prep.add_argument("--isolated-from", type=Path, default=None)
    for name in ("run", "audit", "check", "review", "report"):
        rf.add_parser(name).add_argument("directory", type=Path)
    rf_compare = rf.add_parser("compare")
    rf_compare.add_argument("directory", type=Path)
    rf_compare.add_argument("other", type=Path)
    rf_retry = rf.add_parser("retry")
    rf_retry.add_argument("directory", type=Path)
    rf_retry.add_argument("actors", nargs="+")

    rs = sub.add_parser("relaysearch").add_subparsers(dest="command", required=True)
    rs_prep = rs.add_parser("prepare")
    rs_prep.add_argument("directory", type=Path)
    rs_prep.add_argument("--blocks", type=int, default=12)
    rs_prep.add_argument("--generations", type=int, default=5)
    rs_prep.add_argument("--integrity", choices=["library", "paper"], default="library")
    for name in ("run", "audit", "check", "report"):
        rs.add_parser(name).add_argument("directory", type=Path)
    rs.add_parser("build-corpus")
    rs_retry = rs.add_parser("retry")
    rs_retry.add_argument("directory", type=Path)
    rs_retry.add_argument("actors", nargs="+")

    dv = sub.add_parser("discovery").add_subparsers(dest="command", required=True)
    dv_prep = dv.add_parser("prepare")
    dv_prep.add_argument("directory", type=Path)
    dv_prep.add_argument("--problems", nargs="+", default=None)
    dv_prep.add_argument("--replicates", type=int, default=3)
    for name in ("run", "audit", "check", "report"):
        dv.add_parser(name).add_argument("directory", type=Path)
    dv_retry = dv.add_parser("retry")
    dv_retry.add_argument("directory", type=Path)
    dv_retry.add_argument("actors", nargs="+")

    dc = sub.add_parser("discoverycode").add_subparsers(dest="command", required=True)
    dc_prep = dc.add_parser("prepare")
    dc_prep.add_argument("directory", type=Path)
    dc_prep.add_argument("--problems", nargs="+", default=None)
    dc_prep.add_argument("--replicates", type=int, default=4)
    dc_prep.add_argument("--arms", nargs="+", default=None)
    dc_prep.add_argument("--seed", type=int, default=None)
    for name in ("run", "audit", "check", "report"):
        dc.add_parser(name).add_argument("directory", type=Path)
    dc_retry = dc.add_parser("retry")
    dc_retry.add_argument("directory", type=Path)
    dc_retry.add_argument("actors", nargs="+")

    ms = sub.add_parser("mechspancode").add_subparsers(dest="command", required=True)
    ms_prep = ms.add_parser("prepare")
    ms_prep.add_argument("directory", type=Path)
    ms_prep.add_argument("--problems", nargs="+", default=None)
    ms_prep.add_argument("--replicates", type=int, default=6)
    ms_prep.add_argument("--arms", nargs="+", default=None)
    ms_prep.add_argument("--seed", type=int, default=None)
    for name in ("run", "audit", "check", "report"):
        ms.add_parser(name).add_argument("directory", type=Path)
    ms_retry = ms.add_parser("retry")
    ms_retry.add_argument("directory", type=Path)
    ms_retry.add_argument("actors", nargs="+")

    wr = sub.add_parser("write").add_subparsers(dest="command", required=True)
    wr_prep = wr.add_parser("prepare")
    wr_prep.add_argument("directory", type=Path)
    wr_prep.add_argument("--problems", nargs="+", default=None)
    wr_prep.add_argument("--replicates", type=int, default=3)
    for name in ("run", "audit", "check", "report"):
        wr.add_parser(name).add_argument("directory", type=Path)
    wr_retry = wr.add_parser("retry")
    wr_retry.add_argument("directory", type=Path)
    wr_retry.add_argument("actors", nargs="+")

    wc = sub.add_parser("writecode").add_subparsers(dest="command", required=True)
    wc_prep = wc.add_parser("prepare")
    wc_prep.add_argument("directory", type=Path)
    wc_prep.add_argument("--problems", nargs="+", default=None)
    wc_prep.add_argument("--replicates", type=int, default=3)
    for name in ("run", "audit", "check", "report"):
        wc.add_parser(name).add_argument("directory", type=Path)
    wc_retry = wc.add_parser("retry")
    wc_retry.add_argument("directory", type=Path)
    wc_retry.add_argument("actors", nargs="+")

    tr = sub.add_parser("transmission").add_subparsers(dest="command", required=True)
    tr_prep = tr.add_parser("prepare")
    tr_prep.add_argument("directory", type=Path)
    tr_prep.add_argument("--chains", type=int, default=4)
    tr_prep.add_argument("--generations", type=int, default=4)
    tr_prep.add_argument("--arms", nargs="+", default=None)
    tr_prep.add_argument("--verifier", choices=["hygienic"], default=None)
    for name in ("run", "audit", "check"):
        tr.add_parser(name).add_argument("directory", type=Path)
    tr_report = tr.add_parser("report")
    tr_report.add_argument("directory", type=Path)
    tr_report.add_argument("--csv", type=Path, default=None)
    tr_retry = tr.add_parser("retry")
    tr_retry.add_argument("directory", type=Path)
    tr_retry.add_argument("actors", nargs="+")

    zd = sub.add_parser("zerodoor").add_subparsers(dest="command", required=True)
    zd_prep = zd.add_parser("prepare")
    zd_prep.add_argument("directory", type=Path)
    zd_prep.add_argument("--door", choices=["A4", "A5"], required=True)
    zd_prep.add_argument("--chains", type=int, default=4)
    zd_prep.add_argument("--generations", type=int, default=4)
    zd_prep.add_argument("--arms", nargs="+", default=None)
    for name in ("run", "audit", "check", "report"):
        zd.add_parser(name).add_argument("directory", type=Path)
    zd_retry = zd.add_parser("retry")
    zd_retry.add_argument("directory", type=Path)
    zd_retry.add_argument("actors", nargs="+")
    zd.add_parser("selftest")
    pop = sub.add_parser("population").add_subparsers(dest="command", required=True)
    pop_prep = pop.add_parser("prepare")
    pop_prep.add_argument("directory", type=Path)
    pop_prep.add_argument("--chains", type=int, default=2)
    pop_prep.add_argument("--generations", type=int, default=6)
    pop_prep.add_argument("--agents", type=int, default=4)
    pop_prep.add_argument("--arms", nargs="+", default=None)
    pop_prep.add_argument("--predictions", choices=["t21", "v4pro"], default="t21")
    pop_prep.add_argument("--concurrency-per-arm", type=int, default=None)
    pop_prep.add_argument("--hard-stop", default=None)
    for name in ("run", "audit", "check", "report"):
        pop.add_parser(name).add_argument("directory", type=Path)
    pop_retry = pop.add_parser("retry")
    pop_retry.add_argument("directory", type=Path)
    pop_retry.add_argument("actors", nargs="+")
    pop_ext = pop.add_parser("extend")
    pop_ext.add_argument("directory", type=Path)
    pop_ext.add_argument("--generations", type=int, required=True)
    pop_ext.add_argument("--arms", nargs="+", required=True)

    comp = sub.add_parser("composition").add_subparsers(dest="command", required=True)
    comp_prep = comp.add_parser("prepare")
    comp_prep.add_argument("directory", type=Path)
    comp_prep.add_argument("--arms", nargs="+", default=None)
    comp_prep.add_argument("--reps", type=int, default=4)
    for name in ("run", "audit", "check"):
        comp.add_parser(name).add_argument("directory", type=Path)
    comp_report = comp.add_parser("report")
    comp_report.add_argument("directory", type=Path)
    comp_report.add_argument("--csv", type=Path, default=None)
    comp_retry = comp.add_parser("retry")
    comp_retry.add_argument("directory", type=Path)
    comp_retry.add_argument("actors", nargs="+")
    comp.add_parser("selftest")

    sp = sub.add_parser("spillover").add_subparsers(dest="command", required=True)
    sp_prep = sp.add_parser("prepare")
    sp_prep.add_argument("directory", type=Path)
    sp_prep.add_argument("--chains", type=int, default=2)
    sp_prep.add_argument("--generations", type=int, default=6)
    sp_prep.add_argument(
        "--arms", nargs="+", default=["mixed"],
        help="arms to prepare (default: mixed only, for backward compatibility)",
    )
    for name in ("run", "audit", "check"):
        sp.add_parser(name).add_argument("directory", type=Path)
    sp_report = sp.add_parser("report")
    sp_report.add_argument("directory", type=Path)
    sp_report.add_argument("--csv", type=Path, default=None)
    sp_retry = sp.add_parser("retry")
    sp_retry.add_argument("directory", type=Path)
    sp_retry.add_argument("actors", nargs="+")
    sp.add_parser("selftest")

    code = sub.add_parser("code").add_subparsers(dest="command", required=True)
    code.add_parser("selftest")
    board = sub.add_parser("board").add_subparsers(dest="command", required=True)
    board.add_parser("baseline-prepare").add_argument("directory", type=Path)
    for name in ("baseline-run", "extract", "run", "check", "audit", "review", "report"):
        board.add_parser(name).add_argument("directory", type=Path)
    probes = board.add_parser("prepare")
    probes.add_argument("directory", type=Path)
    probes.add_argument("--phase", choices=["engineering", "formal"], required=True)
    board_retry = board.add_parser("retry")
    board_retry.add_argument("directory", type=Path)
    board_retry.add_argument("actors", nargs="+")

    cont = sub.add_parser("continuation").add_subparsers(dest="command", required=True)
    cont_sel = cont.add_parser("select")
    cont_sel.add_argument("source_run", type=Path, nargs="+")
    cont_sel.add_argument("--out", type=Path, default=Path("report/continuation/selected.csv"))
    cont_prep = cont.add_parser("prepare")
    cont_prep.add_argument("source_run", type=Path)
    cont_prep.add_argument("dest_run", type=Path)
    for name in ("run", "audit", "report"):
        cont.add_parser(name).add_argument("directory", type=Path)
    cont.add_parser("selftest")
    args = parser.parse_args()

    if args.group == "continuation":
        from parabox.studies.continuation.__main__ import dispatch as cont_dispatch
        cont_dispatch(args)
        return

    if args.group == "lean":
        from parabox.tasks.lean.selftest import selftest
        result = selftest()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        raise SystemExit(0 if result["ok"] else 1)
    if args.group == "code":
        from parabox.tasks.code.selftest import selftest
        result = selftest()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        raise SystemExit(0 if result["ok"] else 1)
    if args.group == "board":
        from parabox.studies.board import check as board_check
        from parabox.studies.board import run as board_run
        from parabox.studies.board import score as board_score
        if args.command == "baseline-prepare":
            board_run.prepare_baseline(args.directory)
            print(f"prepared {args.directory}")
        elif args.command == "baseline-run":
            board_run.run_baseline(args.directory)
        elif args.command == "prepare":
            board_run.prepare_probes(args.directory, args.phase)
            print(f"prepared {args.directory}")
        elif args.command == "run":
            board_run.run(args.directory)
        elif args.command == "retry":
            board_run.retry(args.directory, args.actors)
        elif args.command == "extract":
            print(json.dumps(board_run.extract(args.directory)))
        elif args.command == "audit":
            print(json.dumps(board_run.audit(args.directory)))
        elif args.command == "check":
            result = board_check.check(args.directory)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            raise SystemExit(0 if result["ok"] else 1)
        elif args.command == "review":
            board_score.run_review(args.directory)
        elif args.command == "report":
            print(json.dumps(board_score.report(args.directory), ensure_ascii=False, indent=2))
        return

    if args.group == "discovery":
        from parabox.studies.discovery import check as dv_check
        from parabox.studies.discovery import run as dv_run
        from parabox.studies.discovery import score as dv_score
        if args.command == "prepare":
            dv_run.prepare(args.directory, problems=args.problems, replicates=args.replicates)
            print(f"prepared {args.directory}")
        elif args.command == "run":
            dv_run.run(args.directory)
        elif args.command == "retry":
            dv_run.retry(args.directory, args.actors)
        elif args.command == "audit":
            print(json.dumps(dv_run.audit(args.directory)))
        elif args.command == "check":
            result = dv_check.check(args.directory)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            raise SystemExit(0 if result["ok"] else 1)
        elif args.command == "report":
            print(json.dumps(dv_score.report(args.directory), ensure_ascii=False, indent=2))
        return

    if args.group == "discoverycode":
        from parabox.studies.discovery_code import check as dc_check
        from parabox.studies.discovery_code import run as dc_run
        from parabox.studies.discovery_code import score as dc_score
        if args.command == "prepare":
            dc_run.prepare(args.directory, problems=args.problems, replicates=args.replicates,
                           arms=args.arms, seed=args.seed)
            print(f"prepared {args.directory}")
        elif args.command == "run":
            dc_run.run(args.directory)
        elif args.command == "retry":
            dc_run.retry(args.directory, args.actors)
        elif args.command == "audit":
            print(json.dumps(dc_run.audit(args.directory)))
        elif args.command == "check":
            result = dc_check.check(args.directory)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            raise SystemExit(0 if result["ok"] else 1)
        elif args.command == "report":
            print(json.dumps(dc_score.report(args.directory), ensure_ascii=False, indent=2))
        return

    if args.group == "mechspancode":
        from parabox.studies.mechspan_code import check as ms_check
        from parabox.studies.mechspan_code import run as ms_run
        from parabox.studies.mechspan_code import score as ms_score
        if args.command == "prepare":
            ms_run.prepare(args.directory, problems=args.problems, replicates=args.replicates,
                           arms=args.arms, seed=args.seed)
            print(f"prepared {args.directory}")
        elif args.command == "run":
            ms_run.run(args.directory)
        elif args.command == "retry":
            ms_run.retry(args.directory, args.actors)
        elif args.command == "audit":
            print(json.dumps(ms_run.audit(args.directory)))
        elif args.command == "check":
            result = ms_check.check(args.directory)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            raise SystemExit(0 if result["ok"] else 1)
        elif args.command == "report":
            print(json.dumps(ms_score.report(args.directory), ensure_ascii=False, indent=2))
        return

    if args.group == "write":
        from parabox.studies.write import check as wr_check
        from parabox.studies.write import run as wr_run
        from parabox.studies.write import score as wr_score
        if args.command == "prepare":
            wr_run.prepare(args.directory, problems=args.problems, replicates=args.replicates)
            print(f"prepared {args.directory}")
        elif args.command == "run":
            wr_run.run(args.directory)
        elif args.command == "retry":
            wr_run.retry(args.directory, args.actors)
        elif args.command == "audit":
            print(json.dumps(wr_run.audit(args.directory)))
        elif args.command == "check":
            result = wr_check.check(args.directory)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            raise SystemExit(0 if result["ok"] else 1)
        elif args.command == "report":
            print(json.dumps(wr_score.report(args.directory), ensure_ascii=False, indent=2))
        return

    if args.group == "writecode":
        from parabox.studies.write_code import check as wc_check
        from parabox.studies.write_code import run as wc_run
        from parabox.studies.write_code import score as wc_score
        if args.command == "prepare":
            wc_run.prepare(args.directory, problems=args.problems, replicates=args.replicates)
            print(f"prepared {args.directory}")
        elif args.command == "run":
            wc_run.run(args.directory)
        elif args.command == "retry":
            wc_run.retry(args.directory, args.actors)
        elif args.command == "audit":
            print(json.dumps(wc_run.audit(args.directory)))
        elif args.command == "check":
            result = wc_check.check(args.directory)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            raise SystemExit(0 if result["ok"] else 1)
        elif args.command == "report":
            print(json.dumps(wc_score.report(args.directory), ensure_ascii=False, indent=2))
        return

    if args.group == "transmission":
        from parabox.studies.transmission import check as tr_check
        from parabox.studies.transmission import run as tr_run
        from parabox.studies.transmission import score as tr_score
        if args.command == "prepare":
            tr_run.prepare(args.directory, chains=args.chains, generations=args.generations,
                           arms=args.arms, verifier=args.verifier)
            print(f"prepared {args.directory}")
        elif args.command == "run":
            tr_run.run(args.directory)
        elif args.command == "retry":
            tr_run.retry(args.directory, args.actors)
        elif args.command == "audit":
            print(json.dumps(tr_run.audit(args.directory)))
        elif args.command == "check":
            result = tr_check.check(args.directory)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            raise SystemExit(0 if result["ok"] else 1)
        elif args.command == "report":
            print(json.dumps(tr_score.report(args.directory, csv_path=args.csv),
                             ensure_ascii=False, indent=2))
        return

    if args.group == "zerodoor":
        from parabox.studies.transmission_door import check as zd_check
        from parabox.studies.transmission_door import run as zd_run
        from parabox.studies.transmission_door import score as zd_score
        if args.command == "selftest":
            from parabox.studies.transmission_door.selftest import selftest
            result = selftest()
            print(json.dumps(result, ensure_ascii=False, indent=2))
            raise SystemExit(0 if result["ok"] else 1)
        if args.command == "prepare":
            zd_run.prepare(args.directory, door=args.door, chains=args.chains,
                           generations=args.generations, arms=args.arms)
            print(f"prepared {args.directory}")
        elif args.command == "run":
            zd_run.run(args.directory)
        elif args.command == "retry":
            zd_run.retry(args.directory, args.actors)
        elif args.command == "audit":
            print(json.dumps(zd_run.audit(args.directory)))
        elif args.command == "check":
            result = zd_check.check(args.directory)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            raise SystemExit(0 if result["ok"] else 1)
        elif args.command == "report":
            print(json.dumps(zd_score.report(args.directory), ensure_ascii=False, indent=2))
    if args.group == "population":
        from parabox.studies.population import check as pop_check
        from parabox.studies.population import run as pop_run
        from parabox.studies.population import score as pop_score
        if args.command == "prepare":
            from parabox.studies.population import design as pop_D
            preds = pop_D.V4PRO_PREDICTIONS if args.predictions == "v4pro" else pop_D.PREDICTIONS
            pop_run.prepare(args.directory, chains=args.chains, generations=args.generations,
                            agents=args.agents, arms=args.arms, predictions=preds,
                            concurrency_per_arm=args.concurrency_per_arm, hard_stop=args.hard_stop)
            print(f"prepared {args.directory}")
        elif args.command == "run":
            pop_run.run(args.directory)
        elif args.command == "retry":
            pop_run.retry(args.directory, args.actors)
        elif args.command == "extend":
            added = pop_run.extend(args.directory, generations=args.generations, arms=args.arms)
            print(f"extended {args.directory} by {len(added)} sessions")
        elif args.command == "audit":
            print(json.dumps(pop_run.audit(args.directory)))
        elif args.command == "check":
            result = pop_check.check(args.directory)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            raise SystemExit(0 if result["ok"] else 1)
        elif args.command == "report":
            print(json.dumps(pop_score.report(args.directory), ensure_ascii=False, indent=2))
        return

    if args.group == "composition":
        from parabox.studies.composition import check as comp_check
        from parabox.studies.composition import run as comp_run
        from parabox.studies.composition import score as comp_score
        if args.command == "selftest":
            from parabox.studies.composition.selftest import selftest
            result = selftest()
            print(json.dumps(result, ensure_ascii=False, indent=2))
            raise SystemExit(0 if result["ok"] else 1)
        if args.command == "prepare":
            comp_run.prepare(args.directory, arms=args.arms, reps=args.reps)
            print(f"prepared {args.directory}")
        elif args.command == "run":
            comp_run.run(args.directory)
        elif args.command == "retry":
            comp_run.retry(args.directory, args.actors)
        elif args.command == "audit":
            print(json.dumps(comp_run.audit(args.directory)))
        elif args.command == "check":
            result = comp_check.check(args.directory)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            raise SystemExit(0 if result["ok"] else 1)
        elif args.command == "report":
            print(json.dumps(comp_score.report(args.directory, csv_path=args.csv),
                             ensure_ascii=False, indent=2))
        return

    if args.group == "spillover":
        from parabox.studies.spillover import check as sp_check
        from parabox.studies.spillover import run as sp_run
        from parabox.studies.spillover import score as sp_score
        if args.command == "selftest":
            from parabox.studies.spillover.selftest import selftest
            result = selftest()
            print(json.dumps(result, ensure_ascii=False, indent=2))
            raise SystemExit(0 if result["ok"] else 1)
        if args.command == "prepare":
            sp_run.prepare(args.directory, chains=args.chains, generations=args.generations,
                           arms=args.arms)
            print(f"prepared {args.directory}")
        elif args.command == "run":
            sp_run.run(args.directory)
        elif args.command == "retry":
            sp_run.retry(args.directory, args.actors)
        elif args.command == "audit":
            print(json.dumps(sp_run.audit(args.directory)))
        elif args.command == "check":
            result = sp_check.check(args.directory)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            raise SystemExit(0 if result["ok"] else 1)
        elif args.command == "report":
            print(json.dumps(sp_score.report(args.directory, csv_path=args.csv),
                             ensure_ascii=False, indent=2))
        return

    if args.group == "relayboard":
        from parabox.studies.relay_board import check, run, score
    elif args.group == "relayfiles":
        from parabox.studies.relay_files import check, run, score
    elif args.group == "relaysearch":
        from parabox.studies.relay_search import check, run, score
    else:
        from parabox.studies.relay import check, run, score
    if args.command == "build-corpus":
        from parabox.studies.relay_search.corpus import build_corpus
        print(json.dumps({"sha256": build_corpus()["sha256"]}))
    elif args.command == "prepare" and args.group == "relayboard":
        run.prepare(args.directory, blocks=args.blocks, generations=args.generations, integrity=args.integrity,
                    style=args.style, isolated_from=args.isolated_from)
        print(f"prepared {args.directory}")
    elif args.command == "prepare" and args.group == "relayfiles":
        run.prepare(args.directory, blocks=args.blocks, generations=args.generations, integrity=args.integrity,
                    isolated_from=args.isolated_from)
        print(f"prepared {args.directory}")
    elif args.command == "prepare":
        run.prepare(args.directory, blocks=args.blocks, generations=args.generations, integrity=args.integrity)
        print(f"prepared {args.directory}")
    elif args.command == "run":
        run.run(args.directory)
    elif args.command == "retry":
        run.retry(args.directory, args.actors)
    elif args.command == "audit":
        print(json.dumps(run.audit(args.directory)))
    elif args.command == "check":
        result = check.check(args.directory)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        raise SystemExit(0 if result["ok"] else 1)
    elif args.command == "review":
        score.run_review(args.directory)
    elif args.command == "report":
        print(json.dumps(score.report(args.directory), ensure_ascii=False, indent=2))
    elif args.command == "compare":
        print(json.dumps(score.compare(args.directory, args.other), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
