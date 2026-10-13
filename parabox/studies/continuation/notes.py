"""Review notes written during continuation (files in shared/ that were not in the source copy)."""
from __future__ import annotations

import importlib.util
from pathlib import Path

from parabox.studies.continuation.run import _new_notes, session_dir
from parabox.util import save

T15_NOTES = Path("/home/ast/workspaces/parabox-t15-note-reviewer/parabox/review/notes.py")


def _t15():
    spec = importlib.util.spec_from_file_location("t15_review_notes", T15_NOTES)
    if spec is None or spec.loader is None:
        raise SystemExit(f"T15 reviewer is missing: {T15_NOTES}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def review_new_notes(directory: Path, out: Path, *, cache_dir: Path | None = None) -> dict:
    """Two-model reviewer on NEW shared/ files only. Cache defaults to out.parent/cache."""
    directory = Path(directory)
    out = Path(out)
    cache = Path(cache_dir or (out.parent / "cache"))
    notes = _t15()
    raw_sessions = notes.extract_run(directory, run_name=directory.name)
    filtered = []
    for session in raw_sessions:
        actor = session["actor"]
        target = session_dir(directory, actor)
        new_paths = set(_new_notes(target))
        session["notes"] = [item for item in session.get("notes") or [] if item["path"] in new_paths]
        session["wrote_shared"] = bool(session["notes"])
        session["n_writes"] = len(session["notes"])
        if session["notes"]:
            filtered.append(session)
    if not filtered:
        payload = {
            "run": directory.name,
            "run_dir": str(directory),
            "new_notes_only": True,
            "sessions": [],
            "note": "no new shared/ files versus the source copy",
        }
        save(out, payload)
        return payload
    clients = [notes._client(path) for _, path in notes.DEFAULT_MODELS]
    import asyncio
    asyncio.run(notes.review_sessions(filtered, clients, cache, concurrency=notes.CONCURRENCY))
    for session in filtered:
        notes.finalize_session(session)
    payload = {
        "run": directory.name,
        "run_dir": str(directory),
        "new_notes_only": True,
        "prompt_version": notes.PROMPT_VERSION,
        "reviewers": [
            {"name": name, "config": str(path), "model": client.model}
            for (name, path), client in zip(notes.DEFAULT_MODELS, clients)
        ],
        "rule": "final = agreed label and mean confidence >= 5, else disputed",
        "sessions": [notes.strip_for_save(session) for session in filtered],
    }
    save(out, payload)
    return {"out": str(out), "sessions": len(filtered)}
