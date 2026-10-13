"""Render a node snapshot into a directory, and hash whatever is there."""
from __future__ import annotations

import shutil
from pathlib import Path

from parabox.util import digest_json, sha256


def render(files: list[dict], dest: Path) -> None:
    """files items have path and either raw bytes or text. An empty list leaves an empty directory."""
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    for item in files:
        path = dest / item["path"]
        resolved = path.resolve()
        if resolved != dest.resolve() and dest.resolve() not in resolved.parents:
            raise ValueError(f"snapshot path escapes the board: {item['path']}")
        path.parent.mkdir(parents=True, exist_ok=True)
        if item.get("raw") is not None:
            path.write_bytes(item["raw"])
        else:
            path.write_text(item["text"])


def listing(root: Path) -> list[dict]:
    if not root.exists():
        return []
    rows = []
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        rows.append({"path": str(path.relative_to(root)), "sha256": sha256(path.read_bytes())})
    return rows


def listing_sha(rows: list[dict]) -> str:
    return digest_json(rows)
