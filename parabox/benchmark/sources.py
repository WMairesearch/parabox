"""Packaged founder checkpoints and verified exports of mutable wiki files."""

from __future__ import annotations

import copy
import json
from pathlib import Path, PurePosixPath

from parabox.util import sha256
from parabox.workspace import read_regular


BUNDLE = Path(__file__).with_name("assets") / "wiki-founders.json"
BUNDLE_SHA256 = "f0a2b4ab853a42e4419f7778b98c5e9986c68689675a005cfe69e46c20879139"
NOTE = "shared/wiki/NOTES.md"


def wiki_path(name: str) -> str:
    path = PurePosixPath(name)
    if (not name or str(path) != name or path.is_absolute() or ".." in path.parts
            or "\x00" in name or path.parts[:2] != ("shared", "wiki")
            or len(path.parts) < 3):
        raise ValueError("Expected a confined shared/wiki file")
    return name


def content_digest(value: str) -> str:
    if (not isinstance(value, str) or len(value) != 64
            or any(character not in "0123456789abcdef" for character in value)):
        raise ValueError("Expected a SHA-256 digest")
    return value


def initial_payload(block: int, condition: str, checkpoint_author: int = 0) -> dict:
    if (type(block) is not int or block not in range(3)
            or condition not in ("empty_wiki", "artifacts_only", "full_wiki")
            or type(checkpoint_author) is not int or checkpoint_author != 0):
        raise ValueError("Expected a packaged first-author checkpoint and known condition")
    raw = BUNDLE.read_bytes()
    if sha256(raw) != BUNDLE_SHA256:
        raise ValueError("Packaged source bundle digest mismatch")
    bundle = json.loads(raw)
    if bundle["schema_version"] != 1 or bundle["kind"] != "wiki_founder_checkpoints":
        raise ValueError("Unsupported source bundle")
    selected = bundle["blocks"][block]
    if selected["block"] != block or selected["checkpoint_author"] != checkpoint_author:
        raise ValueError("Source checkpoint identity mismatch")
    files = {}
    for name, record in selected["files"].items():
        content = record["text"].encode("utf-8")
        if sha256(content) != content_digest(record["sha256"]):
            raise ValueError("Source artifact digest mismatch")
        files[wiki_path(name)] = content
    provenance = copy.deepcopy(selected["provenance"])
    source_hashes = {name: sha256(content) for name, content in sorted(files.items())}
    if source_hashes != provenance["source_files"]:
        raise ValueError("Source provenance differs from checkpoint bytes")
    source_note_hash = source_hashes.get(NOTE)
    if condition == "empty_wiki":
        files = {}
    removed = files.pop(NOTE, None) if condition == "artifacts_only" else None
    provenance["condition"] = condition
    provenance["delivered_files"] = {
        name: sha256(content) for name, content in sorted(files.items())
    }
    return {
        "files": files, "provenance": provenance,
        "source_note_hash": source_note_hash, "checkpoint_author": checkpoint_author,
        "checkpoint_files": source_hashes,
        "removed_note_original_hash": sha256(removed) if removed is not None else None,
    }


def export_wiki(directory: Path) -> tuple[dict, dict[str, bytes]]:
    end = json.loads(read_regular(directory, "end.json"))
    outgoing = end.get("outgoing", {})
    if (end.get("normal") is not True or end.get("shutdown_verified") is not True
            or outgoing.get("error") or not isinstance(outgoing.get("files"), dict)):
        raise RuntimeError("Unresolved predecessor failure")
    files = {}
    for name, digest in outgoing["files"].items():
        target = wiki_path("shared/wiki/" + name)
        raw = read_regular(directory, "meta/artifacts/" + content_digest(digest))
        if sha256(raw) != digest:
            raise RuntimeError("Predecessor artifact hash mismatch")
        files[target] = raw
    return end, files
