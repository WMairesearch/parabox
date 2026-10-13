#!/usr/bin/env python3
"""Census of turn-truncated sessions across every run directory.

truncated  = session used >= the protocol turn limit and never called `finish`
no_submit  = truncated and never called `submit`
late_art   = truncated, wrote a conftest/state/score artifact, and never submitted after that write
"""
import argparse
import glob
import json
import os
from collections import defaultdict

ART = ("conftest.py",)


def find_turns(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in ("turns", "max_turns", "turn_limit") and isinstance(v, int):
                return v
        for v in obj.values():
            r = find_turns(v)
            if r:
                return r
    elif isinstance(obj, list):
        for v in obj:
            r = find_turns(v)
            if r:
                return r
    return None


def model_of(run):
    for f in ("protocol.json", "descriptors.json", "status.json"):
        p = os.path.join(run, f)
        if os.path.exists(p):
            try:
                s = open(p).read()
            except Exception:
                continue
            for m in ("deepseek-v4-pro", "deepseek-flash", "deepseek-chat", "deepseek-reasoner",
                      "gemini-3.1-pro-preview", "gemini", "kimi", "qwen3.8-max", "qwen3.8-flash", "qwen"):
                if m in s:
                    return m
    return "?"


def calls(session):
    out = []
    for f in sorted(glob.glob(os.path.join(session, "meta", "responses", "*"))):
        try:
            r = json.load(open(f))
        except Exception:
            continue
        if "candidates" in r:
            for c in r.get("candidates") or []:
                for p in (c.get("content") or {}).get("parts", []) or []:
                    if "functionCall" in p:
                        fc = p["functionCall"]
                        out.append((fc.get("name", ""), json.dumps(fc.get("args", {}))))
        else:
            for ch in r.get("choices", []) or []:
                for tc in (ch.get("message") or {}).get("tool_calls") or []:
                    fn = tc.get("function", {})
                    out.append((fn.get("name", ""), fn.get("arguments", "") or ""))
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("roots", nargs="+", help="Explicit directories containing local runs")
    args = parser.parse_args(argv)
    for root in args.roots:
        if not os.path.isdir(root):
            parser.error(f"run root is not a directory: {root}")
    rows = []
    for root in args.roots:
        for run in sorted(glob.glob(os.path.join(root, "*"))):
            sdir = os.path.join(run, "sessions")
            if not os.path.isdir(sdir) or "smoke" in run or run.endswith("-eng"):
                continue
            proto = os.path.join(run, "protocol.json")
            limit = None
            if os.path.exists(proto):
                try:
                    limit = find_turns(json.load(open(proto)))
                except Exception:
                    pass
            model = model_of(run)
            n = tr = ns = la = acc = 0
            for s in sorted(glob.glob(os.path.join(sdir, "*"))):
                resp = glob.glob(os.path.join(s, "meta", "responses", "*"))
                if not resp:
                    continue
                n += 1
                cs = calls(s)
                names = [c[0] for c in cs]
                fin = "finish" in names
                sub_idx = [i for i, c in enumerate(cs) if c[0] == "submit"]
                art_idx = [i for i, (t, a) in enumerate(cs)
                           if t in ("write_file", "run_command") and any(k in a for k in ART)
                           and ("write" in t or ">" in a or "tee" in a)]
                try:
                    subs = json.load(open(os.path.join(s, "meta", "submissions.json")))
                    a = any(x.get("accepted") for x in subs) if isinstance(subs, list) else False
                except Exception:
                    a = False
                acc += a
                is_tr = (limit is not None and len(resp) >= limit and not fin)
                if is_tr and not a:
                    tr += 1
                    if not sub_idx:
                        ns += 1
                    if art_idx and (not sub_idx or max(sub_idx) < max(art_idx)):
                        la += 1
            rows.append((os.path.normpath(run), model, limit, n, acc, tr, ns, la))
    tot = defaultdict(int)
    print(f"{'run':62s} {'model':24s} lim   n  acc  trNA nosub conftest")
    for r in rows:
        print(f"{r[0]:62s} {r[1]:24s} {str(r[2]):4s} {r[3]:4d} {r[4]:4d} {r[5]:5d} {r[6]:5d} {r[7]:5d}")
        for k, v in zip(("n", "acc", "tr", "ns", "la"), r[3:]):
            tot[k] += v
    print("TOTAL", dict(tot))
    bym = defaultdict(lambda: defaultdict(int))
    for r in rows:
        for k, v in zip(("n", "acc", "tr", "ns", "la"), r[3:]):
            bym[r[1]][k] += v
    for m, d in sorted(bym.items()):
        print(f"{m:24s} n={d['n']:4d} acc={d['acc']:4d} truncNotAcc={d['tr']:4d} ({d['tr']/d['n']:.2f}) noSubmit={d['ns']:4d} conftestNoSubmit={d['la']:4d}")


if __name__ == "__main__":
    main()
