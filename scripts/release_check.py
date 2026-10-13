"""Report possible secrets and unsafe release paths without printing their contents."""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path

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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--history", action="store_true")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    result = {"worktree": inspect_worktree(args.root),
              "scope": "Pattern triage only; no guarantee of secret absence or redistribution rights."}
    if args.history:
        result["history"] = inspect_history(args.root)
    output = json.dumps(result, indent=2) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(output)
    print(output)
    raise SystemExit(1 if any(result[key]["findings"] for key in ("worktree", "history") if key in result) else 0)


if __name__ == "__main__":
    main()
