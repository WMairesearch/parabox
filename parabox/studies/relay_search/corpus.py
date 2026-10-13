"""Build and load the frozen neutral corpus for the search relay.

The corpus is Mathlib declaration signatures and docstrings, extracted once, offline, from
the research image (`corpus/Extract.lean`) and written to data/corpus. A session never runs
the extractor: run time only loads the frozen file and checks its hash, so every search is
reproducible. The corpus is neutral and shared by all arms; relevance is decided at search
time by BM25, so that "a search returned something" never reveals the arm.
"""
from __future__ import annotations

import json
from pathlib import Path

from parabox.sandbox import run_once
from parabox.tasks.lean import task as LT
from parabox.util import ROOT, digest_json, read, save

CORPUS_PATH = ROOT / "data" / "corpus" / "mathlib-v4.33.1.json"
CORPUS_SHA = "f59fcfb9a6e4a516799e8d8405629efa329a0212a5cf91ea0dc40047507fcedb"
EXTRACT_LEAN = Path(__file__).resolve().parent / "corpus" / "Extract.lean"
EXTRACT_TIMEOUT_S = 600

# Neutral Mathlib declarations, grouped only to keep the list readable. Unknown names are
# skipped by the extractor, so the frozen file records exactly what the image resolved.
GENERAL = [
    "Set.Infinite", "Set.infinite_univ", "Set.Finite", "Set.mem_setOf_eq", "Set.ext",
    "Set.eq_univ_iff_forall", "Set.infinite_coe_iff", "Function.Injective", "Function.Surjective",
    "Function.iterate_succ", "Function.iterate_add", "Finset.sum_range_succ", "Finset.sum_range_succ_comm",
]
TOPICS = {
    "collatz": ["Nat.even_or_odd", "Nat.not_even_iff_odd", "Nat.div_add_mod", "Nat.even_add_one",
                "Function.iterate_succ_apply", "Nat.one_lt_two_pow"],
    "twin_primes": ["Nat.Prime", "Nat.Prime.two_le", "Nat.Prime.one_lt", "Nat.exists_infinite_primes",
                    "Nat.Prime.eq_one_or_self_of_dvd"],
    "goldbach": ["Nat.Prime", "Even", "Odd", "Nat.even_add", "Nat.exists_infinite_primes"],
    "odd_perfect": ["Nat.Perfect", "Nat.sigma", "Nat.divisors", "Nat.sigma_one_eq_sigmaOne",
                    "Nat.sum_divisors_eq_sum_properDivisors_add_self"],
    "beal": ["Nat.Coprime", "Nat.Coprime.symm", "Nat.gcd", "Nat.gcd_comm", "pow_add", "Nat.pos_pow_of_pos"],
    "three_cubes": ["Int.emod", "Int.ModEq", "Int.add_mul_emod_self", "ZMod", "Int.emod_emod_of_dvd"],
    "riemann": ["Complex.exp", "Complex.abs", "Complex.I", "Complex.cpow", "Complex.ofReal", "riemannZeta"],
    "sendov": ["Polynomial.roots", "Polynomial.degree", "Polynomial.derivative", "Complex.abs",
               "Metric.closedBall", "Metric.ball", "Metric.infDist"],
}


def names() -> list[str]:
    seen, out = set(), []
    for name in GENERAL + [n for problem in LT.POOL for n in TOPICS.get(problem, [])]:
        if name not in seen:
            seen.add(name)
            out.append(name)
    return out


def _render(entry: dict) -> dict:
    body = (entry.get("type", "") + "\n\n" + entry.get("doc", "")).strip()
    return {"name": entry["name"], "title": entry["name"], "body": body}


def build_corpus(image: str = LT.IMAGE) -> dict:
    """Run the extractor in the image and write the frozen corpus file."""
    scratch = CORPUS_PATH.parent / "_build"
    scratch.mkdir(parents=True, exist_ok=True)
    (scratch / "names.txt").write_text("\n".join(names()) + "\n")
    (scratch / "Extract.lean").write_text(EXTRACT_LEAN.read_text())
    code, out, err = run_once(
        image,
        "cd /opt/parabox && lake env lean --run /tmp/corpus/Extract.lean /tmp/corpus/names.txt",
        ["-v", f"{scratch.resolve()}:/tmp/corpus:ro,Z"],
        EXTRACT_TIMEOUT_S,
    )
    if code != 0:
        raise SystemExit(f"corpus extraction failed (exit {code}):\n{(out + err)[-3000:]}")
    line = next((item for item in reversed(out.splitlines()) if item.startswith("[")), "")
    try:
        entries = json.loads(line)
    except json.JSONDecodeError as error:
        raise SystemExit(f"corpus extraction produced no JSON: {error}\n{out[-2000:]}")
    records = [_render(entry) for entry in entries]
    payload = {"toolchain": LT.LEAN_TOOLCHAIN, "mathlib": LT.MATHLIB_REV,
               "requested": len(names()), "records": records}
    save(CORPUS_PATH, payload)
    payload["sha256"] = digest_json(records)
    return payload


def load_corpus() -> list[dict]:
    """Return the frozen corpus records, checking the pinned hash."""
    if not CORPUS_PATH.exists():
        raise SystemExit(f"corpus file is missing: {CORPUS_PATH}. Run build_corpus first.")
    payload = read(CORPUS_PATH)
    records = payload["records"]
    digest = digest_json(records)
    if CORPUS_SHA != "PENDING" and digest != CORPUS_SHA:
        raise SystemExit("corpus hash does not match the pinned value")
    return records


def corpus_sha() -> str:
    return digest_json(load_corpus())
