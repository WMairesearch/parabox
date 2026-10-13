"""One fresh Podman container per session, with no network and only that session's workspace.

The model is called from the host. Credentials never enter the container.
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Limits:
    cpus: str = "4"
    memory: str = "16g"


def image_exists(image: str) -> bool:
    return subprocess.call(["podman", "image", "exists", image], stdout=subprocess.DEVNULL) == 0


@dataclass
class Box:
    name: str
    workspace: Path
    image: str
    limits: Limits = field(default_factory=Limits)
    mounts: tuple[tuple[str, str, str], ...] = ()
    """Extra mounts as (host path, container path, options). Options are podman flags such as ro or rw."""

    def run_argv(self) -> list[str]:
        argv = [
            "podman", "--cgroup-manager", "cgroupfs", "run", "-d", "--name", self.name,
            "--network", "none",
            "--cpus", self.limits.cpus, "--memory", self.limits.memory,
            "-v", f"{self.workspace.resolve()}:/workspace:Z",
        ]
        for host, dest, options in self.mounts:
            parts = [part for part in options.split(",") if part]
            if not any(part in ("z", "Z") for part in parts):
                parts.append("Z")
            argv += ["-v", f"{Path(host).resolve()}:{dest}:{','.join(parts)}"]
        argv += [self.image, "sleep", "infinity"]
        return argv

    def start(self) -> None:
        self.workspace.mkdir(parents=True, exist_ok=True)
        for host, _dest, _options in self.mounts:
            Path(host).mkdir(parents=True, exist_ok=True)
        subprocess.run(["podman", "rm", "-f", self.name], check=False, capture_output=True)
        subprocess.check_call(self.run_argv(), stdout=subprocess.DEVNULL)

    def stop(self) -> None:
        subprocess.run(["podman", "rm", "-f", self.name], check=False, capture_output=True)

    def exec(self, command: str, timeout: int, env: dict[str, str] | None = None) -> tuple[int, str]:
        argv = ["podman", "exec"]
        for key, value in (env or {}).items():
            argv += ["-e", f"{key}={value}"]
        argv += [self.name, "bash", "-lc", command]
        try:
            proc = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
            return proc.returncode, proc.stdout + proc.stderr
        except subprocess.TimeoutExpired as error:
            parts = []
            for chunk in (error.stdout, error.stderr):
                if isinstance(chunk, bytes):
                    chunk = chunk.decode(errors="replace")
                parts.append(chunk or "")
            return 124, "".join(parts) + "\nTIMEOUT"


def run_once(image: str, command: str, mounts: list[str], timeout: int, limits: Limits | None = None) -> tuple[int, str, str]:
    """A throwaway container for research-side checks. Nothing here is shown to a participant."""
    limits = limits or Limits()
    proc = subprocess.run(
        ["podman", "--cgroup-manager", "cgroupfs", "run", "--rm", "--network", "none",
         "--cpus", limits.cpus, "--memory", limits.memory,
         *mounts, image, "bash", "-lc", command],
        capture_output=True, text=True, timeout=timeout,
    )
    return proc.returncode, proc.stdout, proc.stderr
