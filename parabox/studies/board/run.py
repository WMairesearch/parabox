"""Prepare, run, and audit the board study.

Baseline waves share one writable cache directory. A wave starts only after the
previous wave has ended normally. Probes each get a read-only copy of one frozen node.
"""
from __future__ import annotations

import asyncio
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from parabox import model
from parabox.sandbox import Box, Limits, image_exists
from parabox.runner.session import run_session
from parabox.studies.board import board as B
from parabox.studies.board import design as D
from parabox.studies.board import nodes as N
from parabox.tasks.base import run_audit_session
from parabox.tasks.code.spec.problems import problem_hashes
from parabox.tasks.code.task import CACHE_DIR, MAX_SUBMITS, TURNS, CodeTask
from parabox.util import ROOT, digest_json, now, read, save, sha256

SEED_DIR = ROOT / "data" / "seeds" / "board-baseline"
CONCURRENCY = 6
LIMITS = Limits(cpus="2", memory="2g")
INTEGRITY = "plain"


def image_id(image: str) -> str | None:
    proc = subprocess.run(["podman", "image", "inspect", "--format", "{{.Id}}", image], capture_output=True, text=True)
    return proc.stdout.strip() or None


def code_commit() -> dict:
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    dirty = subprocess.run(["git", "status", "--porcelain", "--", "parabox", "data", "configs"], cwd=ROOT,
                           capture_output=True, text=True).stdout.strip()
    return {"head": head or None, "dirty": bool(dirty)}


def manifest_path() -> Path:
    return SEED_DIR / "manifest.json"


def load_manifest() -> dict:
    path = manifest_path()
    if not path.exists():
        raise SystemExit(f"missing {path}; run board extract on a finished baseline first")
    return read(path)


def present_nodes(manifest: dict | None = None) -> list[str]:
    manifest = manifest or load_manifest()
    return [name for name in D.NODES if manifest["nodes"][name]["present"]]


def frozen(task: CodeTask, config: dict, *, phase: str, nodes: list[str], per_node: int, manifest: dict | None) -> dict:
    record = task.prompts_record(integrity=INTEGRITY, shared=False)
    body = {
        "task": task.name,
        "image": task.image,
        "image_id": image_id(task.image),
        "problems": problem_hashes(),
        "prompts_sha256": record["sha256"],
        "rules_sha256": N.rules_record()["sha256"],
        "integrity": INTEGRITY,
        "phase": phase,
        "nodes": nodes,
        "per_node": per_node,
        "model": {key: value for key, value in config.items() if key != "api_key"},
        "model_sha256": digest_json(config),
        "turns": TURNS,
        "max_submits": MAX_SUBMITS,
        "concurrency": CONCURRENCY,
        "container": {"network": "none", "cpus": LIMITS.cpus, "memory": LIMITS.memory},
        "cache_dir": CACHE_DIR,
    }
    if manifest is not None:
        body["manifest_sha256"] = digest_json(manifest)
    return body


def _prepare_common(directory: Path, phase: str, schedule: list[dict], nodes: list[str], per_node: int, manifest: dict | None) -> None:
    if (directory / "protocol.json").exists():
        raise SystemExit(f"{directory} is already prepared")
    task = CodeTask()
    if not image_exists(task.image):
        raise SystemExit(f"image {task.image} is missing")
    counted = list(D.NODES) if phase == "baseline" else nodes
    planned = D.budget(counted)
    if planned > D.MAX_AGENTS:
        raise SystemExit(f"planned sessions {planned} exceed {D.MAX_AGENTS}")
    config = model.load_config()
    directory.mkdir(parents=True, exist_ok=True)
    save(directory / "schedule.json", schedule)
    save(directory / "prompts.json", task.prompts_record(integrity=INTEGRITY, shared=False))
    save(directory / "protocol.json", {
        "study": "board",
        "phase": phase,
        "prepared_at": now(),
        "code_commit": code_commit(),
        "container_prefix": "pbx" + sha256(str(directory.resolve()))[:6],
        "frozen": frozen(task, config, phase=phase, nodes=nodes, per_node=per_node, manifest=manifest),
    })


def prepare_baseline(directory: Path) -> None:
    _prepare_common(directory, "baseline", D.baseline_schedule(), list(D.NODES), 0, None)
    (directory / "board").mkdir(exist_ok=True)


def prepare_probes(directory: Path, phase: str) -> None:
    if phase not in ("engineering", "formal"):
        raise SystemExit("phase must be engineering or formal")
    manifest = load_manifest()
    nodes = present_nodes(manifest)
    per_node = D.ENG_PER_NODE if phase == "engineering" else D.FORMAL_PER_NODE
    seed = D.FORMAL_SEED + (0 if phase == "formal" else 1)
    schedule = D.probe_schedule(nodes, per_node, seed, phase)
    _prepare_common(directory, phase, schedule, nodes, per_node, manifest)
    save(directory / "manifest.json", manifest)
    staged = directory / "nodes"
    for name in nodes:
        src = SEED_DIR / name
        dest = staged / name
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(src, dest)
        got = B.listing(dest)
        expected = manifest["nodes"][name]["files"]
        if got != expected:
            raise SystemExit(f"node {name} files do not match the manifest")


def check_frozen(directory: Path) -> dict:
    protocol = read(directory / "protocol.json")
    task = CodeTask()
    frozen_now = frozen(
        task, model.load_config(),
        phase=protocol["phase"],
        nodes=protocol["frozen"]["nodes"],
        per_node=protocol["frozen"]["per_node"],
        manifest=load_manifest() if protocol["phase"] != "baseline" else None,
    )
    changed = [key for key in frozen_now if frozen_now[key] != protocol["frozen"].get(key)]
    if changed:
        raise SystemExit(f"protocol no longer matches: {', '.join(changed)}")
    return protocol


def session_dir(directory: Path, actor: str) -> Path:
    return directory / "sessions" / actor


def status(directory: Path, **fields) -> None:
    save(directory / "status.json", {"updated_at": now(), **fields})


def _one(directory: Path, protocol: dict, task: CodeTask, client, row: dict, *, mounts) -> dict:
    target = session_dir(directory, row["actor"])
    box = Box(f"{protocol['container_prefix']}-{row['actor']}", target / "workspace", task.image, LIMITS, mounts=mounts)
    return run_session(task, client, box, target, row, integrity=INTEGRITY, shared=False, opening=[])


def _run_rows(directory: Path, rows: list[dict], mounts_for, label: str) -> list[dict]:
    protocol = check_frozen(directory)
    task = CodeTask()
    client = model.Client()

    async def batch() -> list[dict]:
        sem = asyncio.Semaphore(CONCURRENCY)
        done: list[dict] = []

        async def go(row):
            async with sem:
                try:
                    end = await asyncio.to_thread(_one, directory, protocol, task, client, row, mounts=mounts_for(row))
                except Exception as exc:
                    end = {"actor": row["actor"], "normal": False, "error": repr(exc)}
                done.append(end)
                status(directory, state="running", label=label, finished=len(done), of=len(rows), last=row["actor"])
                print(row["actor"], "normal" if end.get("normal") else end.get("error"), flush=True)
                return end

        return await asyncio.gather(*(go(row) for row in rows))

    ends = asyncio.run(batch())
    failed = [end["actor"] for end in ends if not end.get("normal")]
    if failed:
        status(directory, state="stopped", label=label, failed=failed)
        raise SystemExit(f"{label} has abnormal sessions: {', '.join(failed)}. Inspect them, then use retry.")
    return ends


def run_baseline(directory: Path) -> None:
    schedule = read(directory / "schedule.json")
    board = directory / "board"
    board.mkdir(exist_ok=True)
    waves = sorted({row["wave"] for row in schedule})
    for wave in waves:
        rows = []
        seen = B.listing(board)
        for row in schedule:
            if row["wave"] != wave:
                continue
            rows.append({**row, "board_at_start": seen})
        mounts = ((str(board), CACHE_DIR, "rw,z"),)

        def mounts_for(_row, mounts=mounts):
            return mounts

        _run_rows(directory, rows, mounts_for, f"wave {wave}")
        dest = directory / "waves" / f"w{wave:02d}"
        if not dest.exists():
            shutil.copytree(board, dest)
        print(f"wave {wave} barrier", flush=True)
    status(directory, state="complete")


def run_probes(directory: Path) -> None:
    schedule = read(directory / "schedule.json")

    def mounts_for(row):
        src = directory / "nodes" / row["node"]
        dest = session_dir(directory, row["actor"]) / "board"
        if not dest.exists():
            shutil.copytree(src, dest)
        return ((str(dest), CACHE_DIR, "ro"),)

    _run_rows(directory, schedule, mounts_for, "probes")
    status(directory, state="complete")


def run(directory: Path) -> None:
    phase = read(directory / "protocol.json")["phase"]
    if phase == "baseline":
        run_baseline(directory)
    else:
        run_probes(directory)


def retry(directory: Path, actors: list[str]) -> None:
    schedule = {row["actor"]: row for row in read(directory / "schedule.json")}
    phase = read(directory / "protocol.json")["phase"]
    log = read(directory / "retries.json") if (directory / "retries.json").exists() else []
    for actor in actors:
        row = schedule[actor]
        target = session_dir(directory, actor)
        end = read(target / "end.json") if (target / "end.json").exists() else None
        if end and end.get("normal"):
            raise SystemExit(f"{actor} ended normally and is not retried")
        if phase == "baseline":
            later = directory / "waves" / f"w{row['wave'] + 1:02d}"
            if later.exists():
                raise SystemExit(f"{actor} already has a later wave")
        log.append({"actor": actor, "at": now(), "error": end.get("error") if end else None})
        if target.exists():
            shutil.rmtree(target)
    save(directory / "retries.json", log)


def extract(directory: Path) -> dict:
    protocol = read(directory / "protocol.json")
    if protocol["phase"] != "baseline":
        raise SystemExit("extract reads a baseline directory")
    if read(directory / "status.json").get("state") != "complete":
        raise SystemExit("baseline is not complete")
    if manifest_path().exists():
        raise SystemExit(f"{manifest_path()} already exists")
    waves = [directory / "waves" / f"w{wave:02d}" for wave in range(D.BASELINE_WAVES)]
    missing = [str(path) for path in waves if not path.exists()]
    if missing:
        raise SystemExit(f"missing wave snapshots: {', '.join(missing)}")
    classified = N.classify(N.events_from_waves(waves))
    SEED_DIR.mkdir(parents=True, exist_ok=True)
    nodes = {}
    for name in D.NODES:
        node = classified[name]
        B.render(node["files"], SEED_DIR / name)
        files = B.listing(SEED_DIR / name)
        nodes[name] = {
            "present": node["present"],
            "files": files,
            "trigger": node["trigger"],
            "sha256": B.listing_sha(files),
        }
        if files != N.snapshot_files(node):
            raise SystemExit(f"rendered {name} does not match the classified bytes")
    manifest = {
        "extracted_at": now(),
        "baseline": str(directory.resolve()),
        "rules": N.rules_record(),
        "nodes": nodes,
    }
    save(manifest_path(), manifest)
    return {name: nodes[name]["present"] for name in D.NODES}


def audit(directory: Path) -> dict:
    task = CodeTask()
    jobs = []
    for end_path in sorted((directory / "sessions").glob("*/end.json")):
        if not (end_path.parent / "meta" / "audit" / "session.json").exists():
            jobs.append(end_path.parent)

    def one(target: Path) -> dict:
        spec = read(target / "meta" / "spec.json")
        result = run_audit_session(task, target, spec, target / "meta" / "audit" / "scratch")
        save(target / "meta" / "audit" / "session.json", result)
        print(target.name, result["reason"], flush=True)
        return result

    with ThreadPoolExecutor(CONCURRENCY) as pool:
        results = list(pool.map(one, jobs))
    return {"audited": len(results), "errors": sum(item["reason"] == "error" for item in results)}
