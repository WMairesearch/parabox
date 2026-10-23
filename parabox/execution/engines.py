"""Lazy adapters: frozen engines own operational and scoring semantics."""
from __future__ import annotations

from dataclasses import dataclass, field
import importlib
import json
from pathlib import Path

from parabox.util import digest_json

from .artifacts import Outcome, manifest
from .ledger import verify_files
from .merge import final_accepted, snapshot_shared


@dataclass
class Invocation:
    key: str
    directory: Path
    spec: dict
    options: dict = field(default_factory=dict)


class CoreEngine:
    """Factory supplies task/client/box and explicit run_session keyword options."""

    policies = frozenset({"replace", "population_all", "population_accepted"})

    def __init__(self, factory, *, runner=None, exporter=None):
        self.factory = factory
        self.runner = runner
        self.exporter = exporter

    def __call__(self, invocation: Invocation, incoming: dict[str, bytes]) -> Outcome:
        incoming_hashes = manifest(incoming)
        if any(not name.startswith("shared/") for name in incoming):
            raise ValueError("Core shared input must stay under shared/")
        runner = self.runner
        if runner is None:
            from parabox.session import run_session
            runner = run_session
        options = dict(self.factory(invocation))
        if "extra_files" in options:
            raise ValueError("Shared input must be supplied through orchestration")
        delivery = {
            "files": {name: content.decode("utf-8", "replace") for name, content in incoming.items()},
            "shared_sha256": digest_json(incoming_hashes),
            "file_sha256": incoming_hashes,
        }
        supplied = options.get("delivered_record", {})
        if not isinstance(supplied, dict) or any(
                supplied[key] != value for key, value in delivery.items() if key in supplied):
            raise ValueError("Delivery metadata conflicts with incoming bytes")
        options["delivered_record"] = {**supplied, **delivery}
        end = runner(directory=Path(invocation.directory), spec=invocation.spec,
                     extra_files=dict(incoming), **options)
        if end.get("normal") is not True:
            return Outcome(end, {})
        if self.exporter is not None:
            files, accepted = self.exporter(invocation)
        else:
            files = snapshot_shared(Path(invocation.directory))
            submissions = json.loads((Path(invocation.directory) /
                                      "meta/submissions.json").read_text())
            accepted = final_accepted(submissions)
        return Outcome(end, files, accepted)


class FrozenWikiEngine:
    """Only registered wiki entrypoints; no global budget overrides or grading."""

    MODULES = {"base": "parabox.tasks.wiki.episode",
               "budget20": "parabox.tasks.wiki.budget"}
    policies = frozenset({"replace"})

    def __init__(self, *, variant: str, frozen: dict[str, str], runner=None, exporter=None):
        if variant not in self.MODULES:
            raise ValueError("Unsupported wiki engine variant")
        required = self.MODULES[variant].replace(".", "/") + ".py"
        self.frozen = {str(Path(name).resolve()): digest for name, digest in frozen.items()}
        if not any(name.endswith("/" + required) for name in self.frozen):
            raise ValueError("Manifest must bind selected engine")
        if runner is None:
            actual = str(Path(__file__).resolve().parents[2] / required)
            if actual not in self.frozen:
                raise ValueError("Manifest must bind the actual imported engine path")
        self.variant, self.runner, self.exporter = variant, runner, exporter

    def __call__(self, invocation: Invocation, incoming: dict[str, bytes]) -> Outcome:
        verify_files(self.frozen)
        options = dict(invocation.options)
        if set(options) != {"config", "image", "files", "deadline"}:
            raise ValueError("Wiki invocation requires config, image, files, deadline")
        manifest(incoming)
        if self.runner is None:
            module = importlib.import_module(self.MODULES[self.variant])
            if str(Path(module.__file__).resolve()) not in self.frozen:
                raise ValueError("Imported engine is not bound by the manifest")
            runner = module.run_episode
        else:
            runner = self.runner
        end = runner(Path(invocation.directory), invocation.spec,
                     incoming=dict(incoming), **options)
        if end.get("normal") is not True:
            return Outcome(end, {})
        if end.get("shutdown_verified") is not True:
            raise RuntimeError("Wiki export requires verified shutdown")
        if self.exporter is None:
            from parabox.benchmark.sources import export_wiki
            _, files = export_wiki(Path(invocation.directory))
        else:
            files = self.exporter(invocation)
        return Outcome(end, files)
