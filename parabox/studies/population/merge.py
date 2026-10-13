"""Merge a generation of shared/ writes into a cumulative record.

The next record is the previous record plus admitted new files. Modifications
of existing files become prefixed new files; deletions are ignored. On a
name collision between agents, every colliding new file is prefixed with
the agent index. The selected arm admits only files whose author was accepted.
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path

from parabox.util import sha256
from parabox.workspace import snapshot_regular

__all__ = [
    "collect_changes",
    "final_accepted",
    "merge_record",
    "prefixed_name",
    "snapshot_shared",
]


def snapshot_shared(target: Path) -> dict[str, bytes]:
    shared = Path(target)
    if shared.name != "shared":
        shared = Path(target) / "workspace" / "shared"
    return {"shared/" + relative: content for relative, content in snapshot_regular(shared).items()}


def collect_changes(received: dict[str, bytes], written: dict[str, bytes]) -> dict:
    new, modified, deleted = {}, {}, []
    for name, data in written.items():
        prior = received.get(name)
        if prior is None:
            new[name] = data
        elif prior != data:
            modified[name] = data
    for name in received:
        if name not in written:
            deleted.append(name)
    return {"new": new, "modified": modified, "deleted": sorted(deleted)}


def final_accepted(submissions: list[dict] | None) -> bool:
    if not submissions:
        return False
    return bool(submissions[-1].get("accepted"))


def prefixed_name(rel: str, agent: int) -> str:
    path = Path(rel)
    return str(path.with_name(f"a{agent}-{path.name}")).replace("\\", "/")


def _unique_name(rel: str, agent: int, taken: set[str]) -> str:
    name = prefixed_name(rel, agent)
    while name in taken:
        name = prefixed_name(name, agent)
    return name


def merge_record(previous: dict[str, bytes], agents: list[dict], arm: str) -> tuple[dict[str, bytes], dict]:
    """Merge one generation.

    Each item of `agents` has: agent (int), actor (str), accepted (bool),
    received (dict[str,bytes]), written (dict[str,bytes]).
    """
    if arm not in ("all", "selected"):
        raise ValueError(f"unknown arm {arm!r}")
    record = dict(previous)
    agent_meta = []
    pending: list[tuple[int, str, bytes, str]] = []
    per_agent = {}

    for item in sorted(agents, key=lambda row: row["agent"]):
        agent = item["agent"]
        accepted = bool(item["accepted"])
        changes = collect_changes(item["received"], item["written"])
        rejected, admitted, modified_facts = [], [], []
        for name, data in sorted(changes["new"].items()):
            candidate = {"path": name, "sha256": sha256(data), "kind": "new"}
            if arm == "selected" and not accepted:
                rejected.append(candidate)
            else:
                pending.append((agent, name, data, "new"))
                admitted.append(candidate)
        for name, data in sorted(changes["modified"].items()):
            candidate = {"path": name, "sha256": sha256(data), "kind": "modified"}
            modified_facts.append({"path": name, "sha256": sha256(data)})
            if arm == "selected" and not accepted:
                rejected.append(candidate)
            else:
                pending.append((agent, name, data, "modified"))
                admitted.append(candidate)
        ignored = [{"path": name, "kind": "deleted"} for name in changes["deleted"]]
        row = {
            "actor": item.get("actor"),
            "agent": agent,
            "accepted": accepted,
            "admitted": admitted,
            "rejected": rejected,
            "modified_existing": modified_facts,
            "deleted_existing": [name for name in changes["deleted"]],
            "ignored_deletions": ignored,
        }
        agent_meta.append(row)
        per_agent[agent] = row

    new_pending = [(a, n, d, k) for a, n, d, k in pending if k == "new"]
    counts = Counter(name for _, name, _, _ in new_pending)
    taken = set(record)
    placements = []
    for agent, name, data, kind in pending:
        if kind == "modified" or counts[name] > 1:
            dest = _unique_name(name, agent, taken)
        elif name in taken:
            dest = _unique_name(name, agent, taken)
        else:
            dest = name
        taken.add(dest)
        record[dest] = data
        placements.append({
            "agent": agent, "from": name, "to": dest, "kind": kind, "sha256": sha256(data),
        })
        if agent in per_agent:
            for entry in per_agent[agent]["admitted"]:
                if entry["path"] == name and entry.get("as") is None and entry["kind"] == kind:
                    entry["as"] = dest
                    break

    files = {name: sha256(data) for name, data in sorted(record.items())}
    meta = {
        "arm": arm,
        "record_files": files,
        "n_files": len(record),
        "placements": placements,
        "agents": agent_meta,
    }
    return record, meta
