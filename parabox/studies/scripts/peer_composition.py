"""Prepare and run the preregistered Peer composition peer-model experiment."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from parabox.studies.unified.run import prepare
from parabox.util import ROOT, now, read, save, sha256

DIRECTORY = ROOT / "runs" / "peer-composition"
RECIPIENT = "configs/model-deepseek-v4-pro.json"
PEERS = {
    "v4pro": RECIPIENT,
    "gemini": "configs/model-gemini.json",
    "kimi": "configs/model-bailian-kimi-k3.json",
    "qwen-max": "configs/model-bailian-qwen3-8-max.json",
    "ds-flash": "configs/model-deepseek.json",
    "qwen-flash": "configs/model-bailian-qwen3-8-flash.json",
}
HARD_STOP = "2026-10-12T06:35:00+00:00"


def source_hashes() -> dict:
    paths = list((ROOT / "parabox").rglob("*.py"))
    paths += [ROOT / path for path in PEERS.values()]
    paths += [Path(__file__), ROOT / "report/studies/final/peer-composition.md"]
    return {str(path.relative_to(ROOT)): sha256(path.read_bytes()) for path in sorted(set(paths))}


def prepare_all() -> None:
    if (DIRECTORY / "registration.json").exists():
        raise SystemExit("Peer composition is already registered")
    for peer, config in PEERS.items():
        target = DIRECTORY / peer
        if (target / "protocol.json").exists():
            raise SystemExit(f"existing preparation: {target}")
        prepare(target, mode="population", gate="open", arms=["mixed-method"],
                model_config=RECIPIENT, models=[RECIPIENT] * 3 + [config],
                problems=["second_item"], chains=5, agents=4, generations=8,
                merge="all", turns=50, seed=2026101101, concurrency=8,
                hard_stop=HARD_STOP)
    save(DIRECTORY / "registration.json", {
        "registered_at": now(), "planned_sessions": 960, "session_cap": 1000,
        "peers": PEERS, "source_sha256": source_hashes(),
        "protocol_sha256": {peer: sha256((DIRECTORY / peer / "protocol.json").read_bytes())
                            for peer in PEERS},
    })
    print("Registered 960 sessions, no subject calls made.", flush=True)


def run_command(peer: str, command: str, *extra: str) -> int:
    target = DIRECTORY / peer
    with (target / f"{command}.log").open("a") as log:
        result = subprocess.run([sys.executable, "-m", "parabox.studies.unified",
                                 command, str(target), *extra], cwd=ROOT,
                                stdout=log, stderr=subprocess.STDOUT)
    print(peer, command, result.returncode, flush=True)
    return result.returncode


def run_all() -> None:
    registration = read(DIRECTORY / "registration.json")
    if source_hashes() != registration["source_sha256"]:
        raise SystemExit("Peer composition source bytes changed after registration")
    for peer in PEERS:
        target = DIRECTORY / peer
        if sha256((target / "protocol.json").read_bytes()) != registration["protocol_sha256"][peer]:
            raise SystemExit(f"Peer composition protocol changed: {peer}")
        if (target / "sessions").exists():
            raise SystemExit("Use explicit per-condition continuation after inspecting existing sessions")

    def one(peer: str) -> dict:
        codes = {"run": run_command(peer, "run")}
        codes["audit"] = run_command(peer, "audit")
        codes["score"] = run_command(peer, "score", "--out", f"report/final/peer-composition-{peer}.csv")
        codes["check"] = run_command(peer, "check")
        return codes

    with ThreadPoolExecutor(max_workers=6) as pool:
        results = dict(zip(PEERS, pool.map(one, PEERS)))
    save(DIRECTORY / "execution.json", {"finished_at": now(), "commands": results})
    print(json.dumps(results), flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "run"))
    args = parser.parse_args()
    if args.command == "prepare":
        prepare_all()
    else:
        run_all()


if __name__ == "__main__":
    main()
