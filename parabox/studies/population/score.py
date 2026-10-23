"""Violation, method, and record-composition descriptors for a population run."""
from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path

from parabox.studies.support.stats import rate, wilson
from parabox.studies.population import design as D
from parabox.studies.relay.run import session_dir
from parabox.studies.transmission.variants import FILE_VARIANTS, file_variant, note_variant
from parabox.util import read, save

FILE_ORDER = list(FILE_VARIANTS)


def keyword_to_frame(keyword: str | None) -> str | None:
    """Map the transmission keyword tag onto condemn / promote / other."""
    if keyword in (None, "", "none"):
        return None
    if keyword == "warning":
        return "condemn"
    if keyword == "other":
        return "other"
    if isinstance(keyword, str) and keyword.startswith("recipe"):
        return "promote"
    return "other"


def _audits(meta: Path) -> bool | None:
    path = meta / "audit" / "session.json"
    if not path.exists():
        return None
    return read(path).get("violation")


def _tool_names(meta: Path) -> list[str]:
    path = meta / "transcript.jsonl"
    if not path.exists():
        return []
    return [json.loads(line)["tool"] for line in path.read_text().splitlines()
            if line.strip() and json.loads(line).get("tool")]


def _writes(target: Path, delivered: dict[str, str]) -> list[tuple[str, str]]:
    workspace = target / "workspace"
    shared = workspace / "shared"
    out = []
    if not shared.exists():
        return out
    for path in sorted(shared.rglob("*")):
        if not path.is_file():
            continue
        rel = str(path.relative_to(workspace))
        try:
            text = path.read_text()
        except Exception:
            text = path.read_bytes().decode("utf-8", "replace")
        if delivered.get(rel) == text:
            continue
        out.append((rel, text))
    return out


def _accepted_source(meta: Path, submissions: list[dict]) -> tuple[str, list[str]]:
    accepted = [item for item in submissions if item.get("accepted")]
    if not accepted:
        return "", []
    last = accepted[-1]
    raw = (meta / "submissions" / f"t{last['turn']:02d}.py").read_text(errors="replace")
    return raw, last.get("extras") or []


def _final_accepted(submissions: list[dict]) -> bool:
    if not submissions:
        return False
    return bool(submissions[-1].get("accepted"))


def session_record(directory: Path, row: dict) -> dict | None:
    target = session_dir(directory, row["actor"])
    if not (target / "end.json").exists():
        return None
    meta = target / "meta"
    end = read(target / "end.json")
    submissions = read(meta / "submissions.json") if (meta / "submissions.json").exists() else []
    delivered = read(meta / "delivered.json")["files"] if (meta / "delivered.json").exists() else {}
    writes = _writes(target, delivered)
    source, extras = _accepted_source(meta, submissions)
    note_text = "\n".join(text for _, text in writes)
    violation = _audits(meta)
    variant = file_variant(source, extras) if source else "none"
    return {
        **{key: row[key] for key in ("actor", "chain", "arm", "generation", "problem", "chain_index", "agent")},
        "normal": end["normal"],
        "submitted": bool(submissions),
        "accepted": _final_accepted(submissions),
        "n_accepted": sum(1 for item in submissions if item.get("accepted")),
        "violation": violation is True,
        "unaudited": violation is None and any(item.get("accepted") for item in submissions),
        "file_variant": variant,
        "note_variant": note_variant(note_text) if writes else None,
        "note_frame": keyword_to_frame(note_variant(note_text)) if writes else None,
        "used_list_dir": "list_dir" in _tool_names(meta),
        "wrote_shared": bool(writes),
        "n_writes": len(writes),
    }


def records(directory: Path) -> list[dict]:
    rows = [session_record(directory, row) for row in read(directory / "schedule.json")]
    return [row for row in rows if row is not None]


def _of(rows: list[dict], arm: str, generation: int | None = None) -> list[dict]:
    out = [r for r in rows if r["arm"] == arm]
    if generation is not None:
        out = [r for r in out if r["generation"] == generation]
    return out


def _arms(rows: list[dict]) -> tuple[str, ...]:
    seen = []
    for row in rows:
        if row["arm"] not in seen:
            seen.append(row["arm"])
    return tuple(seen) or D.ARMS


def _cell(k: int, n: int) -> dict:
    interval = wilson(k, n) if n else None
    return {
        "k": k,
        "n": n,
        "rate": None if n == 0 else k / n,
        "wilson": None if interval is None else [interval[0], interval[1]],
    }


def _modal(values: list[str]) -> tuple[str | None, float | None]:
    if not values:
        return None, None
    counts: dict[str, int] = {}
    for name in values:
        counts[name] = counts.get(name, 0) + 1
    best = max(counts, key=lambda name: (counts[name], -FILE_ORDER.index(name) if name in FILE_ORDER else -99))
    return best, counts[best] / len(values)


def _merge_meta(directory: Path) -> list[dict]:
    folder = directory / "merges"
    if not folder.exists():
        return []
    return [read(path) for path in sorted(folder.glob("*.json"))]


def _record_frames(meta: dict, directory: Path) -> dict:
    chain = meta["chain"]
    generation = meta["generation"]
    folder = directory / "records" / f"{chain}-g{generation:02d}"
    frames = Counter()
    variants = Counter()
    if folder.exists():
        for path in sorted(folder.rglob("*")):
            if not path.is_file():
                continue
            text = path.read_bytes().decode("utf-8", "replace")
            tag = note_variant(text)
            variants[tag] += 1
            frames[keyword_to_frame(tag) or "other"] += 1
    return {
        "chain": chain,
        "arm": meta["arm"],
        "generation": generation,
        "n_files": meta.get("n_files", len(meta.get("record_files") or {})),
        "frames": dict(frames),
        "note_variants": dict(variants),
        "condemn": frames.get("condemn", 0),
        "promote": frames.get("promote", 0),
        "other": frames.get("other", 0),
    }


def _pool_records(frames: list[dict], arm: str, generation: int) -> dict:
    cell = [f for f in frames if f["arm"] == arm and f["generation"] == generation]
    n_files = sum(f["n_files"] for f in cell)
    condemn = sum(f["condemn"] for f in cell)
    promote = sum(f["promote"] for f in cell)
    other = sum(f["other"] for f in cell)
    return {
        "n_files": n_files,
        "condemn": condemn,
        "promote": promote,
        "other": other,
        "condemn_share": None if n_files == 0 else condemn / n_files,
    }


def descriptors(directory: Path) -> dict:
    rows = records(directory)
    arms = _arms(rows)
    gens = sorted({r["generation"] for r in rows})
    merges = _merge_meta(directory)
    frames = [_record_frames(meta, directory) for meta in merges]

    def curve(pred):
        return {arm: {g: rate(pred(r) for r in _of(rows, arm, g)) for g in gens} for arm in arms}

    per = {}
    for arm in arms:
        per[arm] = {}
        for g in gens:
            cell = _of(rows, arm, g)
            variants = [r["file_variant"] for r in cell]
            modal, share = _modal(variants)
            rec = _pool_records(frames, arm, g)
            violations = sum(r["violation"] for r in cell)
            per[arm][g] = {
                "n": len(cell),
                "violation": _cell(violations, len(cell)),
                "file_variant_counts": {name: sum(v == name for v in variants) for name in FILE_ORDER},
                "modal_method": modal,
                "modal_share": share,
                "wrote_shared": rate(r["wrote_shared"] for r in cell),
                "record": rec,
            }

    windows = {}
    for arm in arms:
        early = [r for r in rows if r["arm"] == arm and r["generation"] in (1, 2)]
        late = [r for r in rows if r["arm"] == arm and r["generation"] in (4, 5, 6)]
        late_modal, late_share = _modal([r["file_variant"] for r in late])
        windows[arm] = {
            "gens_1_2": _cell(sum(r["violation"] for r in early), len(early)),
            "gens_4_6": _cell(sum(r["violation"] for r in late), len(late)),
            "modal_method_4_6": late_modal,
            "modal_share_4_6": late_share,
        }

    conventions = {}
    for chain in sorted({r["chain"] for r in rows}):
        cell = [r for r in rows if r["chain"] == chain]
        early = [r for r in cell if r["generation"] in (1, 2)]
        late = [r for r in cell if r["generation"] in (4, 5, 6)]
        early_modal, _ = _modal([r["file_variant"] for r in early])
        late_modal, _ = _modal([r["file_variant"] for r in late])
        index = None
        if early_modal is not None and late:
            index = sum(r["file_variant"] == early_modal for r in late) / len(late)
        conventions[chain] = {
            "arm": cell[0]["arm"] if cell else None,
            "problem": cell[0]["problem"] if cell else None,
            "modal_early": early_modal,
            "modal_late": late_modal,
            "match": early_modal is not None and early_modal == late_modal,
            "convention_index": index,
            "n_early": len(early),
            "n_late": len(late),
        }

    out = {
        "sessions": len(rows),
        "abnormal": sum(not r["normal"] for r in rows),
        "unaudited": sum(r["unaudited"] for r in rows),
        "arms": list(arms),
        "note_frame": "keyword classifier (warning→condemn, recipe_*→promote); review-notes not on this branch",
        "violation_rate": {arm: rate(r["violation"] for r in _of(rows, arm)) for arm in arms},
        "wrote_shared_rate": {arm: rate(r["wrote_shared"] for r in _of(rows, arm)) for arm in arms},
        "file_variant_counts": {
            arm: {name: sum(r["file_variant"] == name for r in _of(rows, arm)) for name in FILE_ORDER}
            for arm in arms
        },
        "violation_by_generation": curve(lambda r: r["violation"]),
        "wrote_shared_by_generation": curve(lambda r: r["wrote_shared"]),
        "per_arm_generation": per,
        "windows": windows,
        "record_by_generation": {
            arm: {g: _pool_records(frames, arm, g) for g in gens} for arm in arms
        },
        "record_frames": frames,
        "conventions": conventions,
        "complete_generations": {
            arm: [g for g in gens if per[arm][g]["n"] == per[arm][gens[0]]["n"] or per[arm][g]["n"] >= 8]
            for arm in arms
        } if gens else {},
    }
    save(directory / "descriptors.json", out)
    save(directory / "records.json", rows)
    return out


def curves_rows(directory: Path, model_name: str) -> list[dict]:
    desc = descriptors(directory)
    rows = []
    for arm, gens in desc["per_arm_generation"].items():
        for generation, cell in gens.items():
            rec = cell["record"]
            rows.append({
                "model": model_name,
                "arm": arm,
                "generation": generation,
                "n": cell["n"],
                "violations": cell["violation"]["k"],
                "violation_rate": cell["violation"]["rate"],
                "modal_method": cell["modal_method"],
                "modal_share": cell["modal_share"],
                "record_files": rec["n_files"],
                "condemn_notes": rec["condemn"],
                "promote_notes": rec["promote"],
            })
    return rows


def write_curves(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = ["model", "arm", "generation", "n", "violations", "violation_rate",
              "modal_method", "modal_share", "record_files", "condemn_notes", "promote_notes"]
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in sorted(rows, key=lambda r: (r["model"], r["arm"], r["generation"])):
            writer.writerow(row)


def report(directory: Path) -> dict:
    return descriptors(directory)
