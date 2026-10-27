"""Explicit Peer composition continuation with a shared, conservative retry budget."""
from __future__ import annotations

import argparse
import fcntl
import subprocess
import sys

from parabox.studies.unified.run import abnormal_actors, past_deadline
from parabox.util import now, read, save
from parabox.studies.scripts.peer_composition import DIRECTORY, HARD_STOP, PEERS, run_command


def continue_peer(peer: str) -> None:
    target = DIRECTORY / peer
    if past_deadline(HARD_STOP):
        raise SystemExit("No Peer composition continuation after the start cutoff")
    actors = abnormal_actors(target)
    if not actors:
        raise SystemExit("No abnormal sessions: inspect state before continuing")
    with (DIRECTORY / "retry-budget.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        path = DIRECTORY / "retry-budget.json"
        ledger = read(path) if path.exists() else []
        reserved = sum(len(entry["actors"]) for entry in ledger)
        if 960 + reserved + len(actors) > 1000:
            raise SystemExit("Peer composition session cap would be exceeded")
        ledger.append({"reserved_at": now(), "peer": peer, "actors": actors})
        save(path, ledger)
    logfile = target / f"continuation-{len(ledger)}.log"
    with logfile.open("x") as handle:
        result = subprocess.run(
            [sys.executable, "-m", "parabox.studies.unified", "retry", str(target), *actors],
            stdout=handle, stderr=subprocess.STDOUT,
        )
    print(peer, "continuation", result.returncode, flush=True)
    for command, extra in (("audit", []), ("score", ["--out", f"report/final/peer-composition-{peer}.csv"]),
                           ("check", [])):
        run_command(peer, command, *extra)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("peer", choices=PEERS)
    continue_peer(parser.parse_args().peer)


if __name__ == "__main__":
    main()
