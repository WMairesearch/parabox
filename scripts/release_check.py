"""Report possible secrets and unsafe release paths without printing their contents."""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import tarfile
import zipfile
from pathlib import Path, PurePosixPath

PATTERNS = {
    "private-key": re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "provider-key": re.compile(rb"\bsk-[A-Za-z0-9_-]{24,}\b"),
    "google-key": re.compile(rb"\bAIza[0-9A-Za-z_-]{35}\b"),
    "aws-access-key": re.compile(rb"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
    "literal-api-key": re.compile(rb'''["']api_key["']\s*:\s*["']([A-Za-z0-9_-]{20,})["']'''),
}


def scan_bytes(content: bytes) -> list[str]:
    return [name for name, pattern in PATTERNS.items() if pattern.search(content)]


def git(root: Path, *args: str) -> bytes:
    return subprocess.check_output(["git", "-C", str(root), *args])


def inspect_worktree(root: Path) -> dict:
    names = set(git(root, "ls-files", "-z").decode().split("\0"))
    names.update(git(root, "ls-files", "--others", "--exclude-standard", "-z").decode().split("\0"))
    findings = []
    checked = 0
    for name in sorted(names - {""}):
        path = root / name
        if not path.exists() and not path.is_symlink():
            continue
        if path.is_symlink():
            findings.append({"path": name, "kind": "symlink-review"})
            continue
        if name.startswith("runs/") or (path.name.startswith(".env") and path.name != ".env.example"):
            findings.append({"path": name, "kind": "private-evidence-or-env"})
            continue
        if path.is_file():
            checked += 1
            findings.extend({"path": name, "kind": kind} for kind in scan_bytes(path.read_bytes()))
    return {"files_checked": checked, "findings": findings}


def inspect_history(root: Path) -> dict:
    objects = []
    for line in git(root, "rev-list", "--objects", "--all").decode().splitlines():
        parts = line.split(" ", 1)
        if len(parts) == 2:
            objects.append(parts)
    findings = []
    count = 0
    process = subprocess.Popen(["git", "-C", str(root), "cat-file", "--batch"],
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    try:
        for object_id, name in objects:
            process.stdin.write((object_id + "\n").encode())
            process.stdin.flush()
            header = process.stdout.readline().decode().split()
            if len(header) != 3:
                raise RuntimeError("cannot read history object")
            size = int(header[2])
            content = process.stdout.read(size)
            if len(content) != size or process.stdout.read(1) != b"\n":
                raise RuntimeError("incomplete history object")
            if header[1] != "blob":
                continue
            count += 1
            if Path(name).name.startswith(".env") and Path(name).name != ".env.example":
                findings.append({"object": object_id, "path": name, "kind": "historical-env"})
            findings.extend({"object": object_id, "path": name, "kind": kind}
                            for kind in scan_bytes(content))
    finally:
        process.stdin.close()
        process.stdout.close()
        process.wait()
    return {"blobs_checked": count, "findings": findings}


def inspect_archive(root: Path, archive: Path) -> dict:
    allowed = {
        line.removeprefix("include ")
        for line in (root / "MANIFEST.in").read_text().splitlines()
        if line.startswith(("include docs/", "include report/"))
    }
    findings, checked = [], 0

    def inspect(name, content, regular=True):
        nonlocal checked
        checked += 1
        relative = PurePosixPath(name)
        if (relative.is_absolute() or ".." in relative.parts or "\\" in name
                or not regular):
            findings.append({"path": name, "kind": "unsafe-archive-entry"})
            return
        if (any(part in {".git", ".venv", "__pycache__", "runs"} for part in relative.parts)
                or (relative.name.startswith(".env") and relative.name != ".env.example")):
            findings.append({"path": name, "kind": "private-evidence-or-env"})
        if name.startswith(("docs/", "report/")) and name not in allowed:
            findings.append({"path": name, "kind": "unlisted-document"})
        findings.extend({"path": name, "kind": kind} for kind in scan_bytes(content))

    if archive.suffix == ".whl":
        with zipfile.ZipFile(archive) as package:
            for entry in package.infolist():
                if not entry.is_dir():
                    inspect(entry.filename, package.read(entry),
                            regular=(entry.external_attr >> 16) & 0o170000 != 0o120000)
    elif archive.name.endswith(".tar.gz"):
        prefix = archive.name.removesuffix(".tar.gz")
        with tarfile.open(archive, "r:gz") as package:
            for entry in package.getmembers():
                if entry.isdir():
                    continue
                name = entry.name.removeprefix(prefix + "/")
                if not entry.name.startswith(prefix + "/"):
                    findings.append({"path": entry.name, "kind": "unexpected-archive-root"})
                stream = package.extractfile(entry) if entry.isfile() else None
                inspect(name, stream.read() if stream else b"", regular=entry.isfile())
    else:
        raise ValueError("Expected a wheel or source .tar.gz archive")
    return {"archive": archive.name, "files_checked": checked, "findings": findings}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--history", action="store_true")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--archive", type=Path, action="append", default=[])
    args = parser.parse_args()
    result = {"worktree": inspect_worktree(args.root),
              "scope": "Pattern triage only; no guarantee of secret absence or redistribution rights."}
    if args.history:
        result["history"] = inspect_history(args.root)
    if args.archive:
        result["archives"] = [inspect_archive(args.root, archive) for archive in args.archive]
    output = json.dumps(result, indent=2) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(output)
    print(output)
    found = any(result[key]["findings"] for key in ("worktree", "history") if key in result)
    found = found or any(record["findings"] for record in result.get("archives", []))
    raise SystemExit(1 if found else 0)


if __name__ == "__main__":
    main()
