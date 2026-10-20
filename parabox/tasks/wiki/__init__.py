"""Portable shared-workspace task; default entrypoint uses 20 execution units."""

from .budget import run_episode, workspace_files

__all__ = ["run_episode", "workspace_files"]
