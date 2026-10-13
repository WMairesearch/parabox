"""Descriptor-relative access to regular files in an untrusted workspace."""
from __future__ import annotations

import os
import shutil
import stat
from contextlib import contextmanager
from pathlib import Path, PurePosixPath

MAX_ARTIFACT_BYTES = 4 * 1024 * 1024


def _parts(relative: str) -> tuple[str, ...]:
    path = PurePosixPath(relative)
    if not relative or path.is_absolute() or ".." in path.parts or "\x00" in relative or not path.parts:
        raise ValueError("artifact path must be relative and confined to the workspace")
    return path.parts


@contextmanager
def _parent(root: Path, relative: str, *, create: bool = False):
    parts = _parts(relative)
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    descriptor = os.open(root, flags)
    try:
        for part in parts[:-1]:
            if create:
                try:
                    os.mkdir(part, mode=0o755, dir_fd=descriptor)
                except FileExistsError:
                    pass
            child = os.open(part, flags, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        yield descriptor, parts[-1]
    finally:
        os.close(descriptor)


def _read_from(parent: int, name: str, limit: int) -> bytes:
    descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
    with os.fdopen(descriptor, "rb") as handle:
        metadata = os.fstat(handle.fileno())
        if not stat.S_ISREG(metadata.st_mode):
            raise ValueError("artifact is not a regular file")
        if metadata.st_size > limit:
            raise ValueError("artifact exceeds the size limit")
        result = handle.read(limit + 1)
        if len(result) > limit:
            raise ValueError("artifact exceeds the size limit")
        return result


def read_regular(root: Path, relative: str, *, limit: int = MAX_ARTIFACT_BYTES) -> bytes:
    """Reject symbolic links, special files, traversal, and oversized artifacts."""
    if limit < 0:
        raise ValueError("limit must be nonnegative")
    with _parent(root, relative) as (parent, name):
        return _read_from(parent, name, limit)


def write_regular(root: Path, relative: str, content: bytes) -> None:
    """Create or replace a regular file without following agent-created links."""
    with _parent(root, relative, create=True) as (parent, name):
        flags = os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK
        descriptor = os.open(name, flags, mode=0o600, dir_fd=parent)
        with os.fdopen(descriptor, "wb") as handle:
            if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
                raise ValueError("artifact is not a regular file")
            os.ftruncate(handle.fileno(), 0)
            handle.write(content)


def read_optional(root: Path, relative: str) -> bytes:
    """Read a regular artifact, treating only a missing path as empty."""
    try:
        return read_regular(root, relative)
    except FileNotFoundError:
        return b""


def list_directory(root: Path, relative: str = ".", *, max_entries: int = 4096) -> list[str]:
    """List a confined directory without following links to classify its entries."""
    with _parent(root, relative + "/.listing") as (parent, _name):
        names = []
        with os.scandir(parent) as entries:
            for entry in entries:
                if len(names) >= max_entries:
                    raise ValueError("directory exceeds the entry limit")
                names.append(entry.name + ("/" if entry.is_dir(follow_symlinks=False) else ""))
        return sorted(names)


def unlink_regular(root: Path, relative: str) -> None:
    """Remove a directory entry without following it; parent links are rejected."""
    try:
        with _parent(root, relative) as (parent, name):
            os.unlink(name, dir_fd=parent)
    except FileNotFoundError:
        pass


def remove_tree(root: Path, relative: str) -> None:
    """Remove a subtree without following directory links on the host."""
    if not shutil.rmtree.avoids_symlink_attacks:
        raise RuntimeError("safe tree removal requires descriptor-relative rmtree")
    try:
        with _parent(root, relative) as (parent, name):
            metadata = os.stat(name, dir_fd=parent, follow_symlinks=False)
            if stat.S_ISDIR(metadata.st_mode):
                shutil.rmtree(name, dir_fd=parent)
            else:
                os.unlink(name, dir_fd=parent)
    except FileNotFoundError:
        pass


def snapshot_regular(root: Path, *, max_entries: int = 4096,
                     max_bytes: int = 16 * 1024 * 1024, max_depth: int = 32) -> dict[str, bytes]:
    """Read a bounded tree of regular files, excluding symlinks and special files."""
    if min(max_entries, max_bytes, max_depth) < 0:
        raise ValueError("snapshot limits must be nonnegative")
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    try:
        descriptor = os.open(root, flags)
    except FileNotFoundError:
        return {}
    result = {}
    entries_seen = total_bytes = 0

    def visit(parent: int, prefix: str, depth: int) -> None:
        nonlocal entries_seen, total_bytes
        if depth > max_depth:
            raise ValueError("artifact tree exceeds the depth limit")
        with os.scandir(parent) as entries:
            for entry in entries:
                entries_seen += 1
                if entries_seen > max_entries:
                    raise ValueError("artifact tree exceeds the entry limit")
                relative = prefix + entry.name
                if entry.is_dir(follow_symlinks=False):
                    child = os.open(entry.name, flags, dir_fd=parent)
                    try:
                        visit(child, relative + "/", depth + 1)
                    finally:
                        os.close(child)
                elif entry.is_file(follow_symlinks=False):
                    content = _read_from(parent, entry.name, min(MAX_ARTIFACT_BYTES, max_bytes - total_bytes))
                    total_bytes += len(content)
                    result[relative] = content

    try:
        visit(descriptor, "", 0)
    finally:
        os.close(descriptor)
    return dict(sorted(result.items()))
