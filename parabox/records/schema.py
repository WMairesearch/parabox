"""Common observations with explicit provenance and native scientific units."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import re
from pathlib import Path


VERSION = 1
STATUSES = {"observed", "unknown", "not_measured", "not_applicable", "unavailable"}
KINDS = {"episode", "aggregate", "finding"}


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def identifier(*parts: str) -> str:
    return digest(json.dumps(parts, ensure_ascii=False, separators=(",", ":")).encode())


def pointer_part(value: object) -> str:
    return str(value).replace("~", "~0").replace("/", "~1")


def resolve_pointer(value, pointer: str):
    if pointer == "":
        return value
    if not pointer.startswith("/"):
        raise ValueError("Evidence pointers must be empty or start with /")
    current = value
    for raw in pointer.split("/")[1:]:
        if re.search(r"~(?![01])", raw):
            raise ValueError("Invalid JSON pointer escape")
        part = raw.replace("~1", "/").replace("~0", "~")
        if isinstance(current, list):
            if not part.isdigit() or (part.startswith("0") and part != "0"):
                raise ValueError("Invalid array index")
            current = current[int(part)]
        elif isinstance(current, dict):
            current = current[part]
        else:
            raise ValueError("Evidence pointer traverses a scalar")
    return current


def _reject_constant(value):
    raise ValueError(f"Non-finite JSON number: {value}")


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON field: {key}")
        result[key] = value
    return result


def parse(raw: bytes, format: str):
    if format == "json":
        value = json.loads(raw, parse_constant=_reject_constant, object_pairs_hook=_unique_object)
        _json_value(value)
        return value
    if format == "jsonl":
        return [parse(line.encode(), "json") for line in raw.decode().splitlines() if line.strip()]
    if format == "csv":
        return list(csv.reader(io.StringIO(raw.decode())))
    if format == "text":
        return raw.decode()
    raise ValueError(f"Unknown source format: {format}")


class Source:
    def __init__(self, path: str | Path, *, root: str | Path, role: str = "saved_result",
                 format: str | None = None):
        self.path = Path(path).resolve()
        root = Path(root).resolve()
        raw = self.path.read_bytes()
        self.format = format or {".json": "json", ".jsonl": "jsonl", ".csv": "csv"}.get(
            self.path.suffix.lower(), "text")
        self.data = parse(raw, self.format)
        self.sha256 = digest(raw)
        self.name = self.path.relative_to(root).as_posix() if self.path.is_relative_to(root) else str(self.path)
        self.id = identifier(self.name, self.sha256)
        self.record = {"id": self.id, "path": self.name, "sha256": self.sha256,
                       "format": self.format, "role": role, "bytes": len(raw)}

    def ref(self, pointer: str = "") -> dict:
        resolve_pointer(self.data, pointer)
        return {"source": self.id, "pointer": pointer}


class Bundle:
    def __init__(self, study: str, adapter: str, *, root: str | Path = ".",
                 metadata: dict | None = None):
        if not study or not adapter:
            raise ValueError("Study and adapter identifiers are required")
        self.root = Path(root).resolve()
        self._sources: dict[str, Source] = {}
        self.data = {"schema_version": VERSION, "study": study,
                     "adapter": {"name": adapter, "version": 1},
                     "metadata": metadata or {}, "sources": [], "records": [], "relations": []}

    def source(self, path: str | Path, *, role: str = "saved_result",
               format: str | None = None) -> Source:
        path = Path(path)
        source = Source(path if path.is_absolute() else self.root / path,
                        root=self.root, role=role, format=format)
        if source.id not in self._sources:
            self._sources[source.id] = source
            self.data["sources"].append(source.record)
        elif self._sources[source.id].record != source.record:
            raise ValueError("Conflicting source metadata")
        return self._sources[source.id]

    def record(self, key: str, *, kind: str = "episode", actor: str | None = None,
               run: str | None = None, role: str = "unknown", model: str | None = None,
               canonical_key: str | None = None, units: dict | None = None,
               assignment: dict | None = None, status: dict | None = None,
               evidence: list[dict] | None = None, attributes: dict | None = None) -> dict:
        record = {"id": identifier(self.data["study"], key), "key": key, "kind": kind,
                  "actor": actor, "run": run, "role": role, "model": model,
                  "canonical_key": canonical_key, "units": units or {},
                  "assignment": assignment or {}, "status": status or {},
                  "evidence": evidence or [], "attributes": attributes or {},
                  "measurements": [], "events": []}
        self.data["records"].append(record)
        return record

    def measure(self, record: dict, name: str, value, *, unit: str, definition: str,
                evidence: list[dict], status: str | None = None) -> dict:
        item = {"name": name, "value": value, "unit": unit, "definition": definition,
                "status": status or ("unknown" if value is None else "observed"),
                "evidence": evidence}
        record["measurements"].append(item)
        return item

    def event(self, record: dict, kind: str, sequence: int, *, evidence: list[dict],
              attributes: dict | None = None, at: str | None = None) -> dict:
        item = {"kind": kind, "sequence": sequence, "at": at,
                "attributes": attributes or {}, "evidence": evidence}
        record["events"].append(item)
        return item

    def relation(self, source: dict, target: dict, kind: str, *, evidence: list[dict],
                 attributes: dict | None = None) -> dict:
        item = {"source": source["id"], "target": target["id"], "kind": kind,
                "evidence": evidence, "attributes": attributes or {}}
        self.data["relations"].append(item)
        return item

    def finish(self) -> dict:
        validate(self.data, sources=self._sources)
        return self.data


def _string(value, label: str, *, nullable: bool = False):
    if nullable and value is None:
        return
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be a nonempty string")


def _json_value(value):
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("Non-finite numbers are not evidence")
    if isinstance(value, dict):
        if any(not isinstance(key, str) for key in value):
            raise ValueError("Object keys must be strings")
        for item in value.values():
            _json_value(item)
    elif isinstance(value, list):
        for item in value:
            _json_value(item)
    elif value is not None and not isinstance(value, (str, int, float, bool)):
        raise ValueError("Evidence must be JSON-compatible")


def validate(bundle: dict, *, sources: dict[str, Source] | None = None) -> dict:
    _json_value(bundle)
    if not isinstance(bundle, dict):
        raise ValueError("An evidence bundle must be an object")
    if type(bundle.get("schema_version")) is not int or bundle["schema_version"] != VERSION:
        raise ValueError("Unsupported evidence schema version")
    _string(bundle.get("study"), "study")
    adapter = bundle.get("adapter", {})
    if not isinstance(adapter, dict):
        raise ValueError("Adapter must be an object")
    _string(adapter.get("name"), "adapter name")
    if type(adapter.get("version")) is not int or adapter["version"] < 1:
        raise ValueError("Positive adapter version required")
    if not isinstance(bundle.get("metadata"), dict):
        raise ValueError("Metadata must be an object")
    for field in ("sources", "records", "relations"):
        if not isinstance(bundle.get(field), list):
            raise ValueError(f"{field} must be a list")
    source_ids = set()
    for source in bundle["sources"]:
        if not isinstance(source, dict):
            raise ValueError("Source entries must be objects")
        _string(source.get("path"), "source path")
        _string(source.get("role"), "source role")
        checksum = source.get("sha256")
        if not isinstance(checksum, str) or len(checksum) != 64 or any(
                character not in "0123456789abcdef" for character in checksum):
            raise ValueError("Invalid source digest")
        if source.get("id") != identifier(source["path"], checksum) or source["id"] in source_ids:
            raise ValueError("Invalid or duplicate source identity")
        if source.get("format") not in {"json", "jsonl", "csv", "text"}:
            raise ValueError("Invalid source format")
        if type(source.get("bytes")) is not int or source["bytes"] < 0:
            raise ValueError("Invalid source size")
        source_ids.add(source["id"])

    def refs(items):
        if not isinstance(items, list) or not items:
            raise ValueError("Observations require evidence references")
        for item in items:
            if not isinstance(item, dict) or item.get("source") not in source_ids:
                raise ValueError("Unknown evidence source")
            pointer = item.get("pointer")
            if not isinstance(pointer, str) or (pointer and not pointer.startswith("/")):
                raise ValueError("Invalid evidence pointer")
            if sources is not None:
                if item["source"] not in sources:
                    raise ValueError("Missing loaded source")
                resolve_pointer(sources[item["source"]].data, pointer)

    record_ids = set()
    canonical_ids = set()
    for record in bundle["records"]:
        if not isinstance(record, dict):
            raise ValueError("Records must be objects")
        _string(record.get("key"), "record key")
        if record.get("id") != identifier(bundle["study"], record["key"]) or record["id"] in record_ids:
            raise ValueError("Invalid or duplicate record identity")
        record_ids.add(record["id"])
        if record.get("kind") not in KINDS:
            raise ValueError("Unknown record kind")
        for field in ("actor", "run", "model", "canonical_key"):
            _string(record.get(field), field, nullable=True)
        _string(record.get("role"), "role")
        if record["kind"] == "episode" and record["actor"] is None:
            raise ValueError("Episodes require an actor")
        canonical = record["canonical_key"]
        if record["kind"] == "episode" and canonical is not None:
            if canonical in canonical_ids:
                raise ValueError("Duplicate canonical episode; retain aliases as metadata or relations")
            canonical_ids.add(canonical)
        for field in ("units", "assignment", "status", "attributes"):
            if not isinstance(record.get(field), dict):
                raise ValueError(f"{field} must be an object")
        for field in ("planned", "started", "ended", "normal"):
            if field in record["status"] and record["status"][field] is not None and type(record["status"][field]) is not bool:
                raise ValueError(f"{field} must be boolean or unknown")
        if record["status"].get("ended") is True and record["status"].get("started") is False:
            raise ValueError("An ended episode cannot be unstarted")
        refs(record.get("evidence"))
        if not isinstance(record.get("measurements"), list) or not isinstance(record.get("events"), list):
            raise ValueError("Measurements and events must be lists")
        names = set()
        for measurement in record["measurements"]:
            if not isinstance(measurement, dict):
                raise ValueError("Measurements must be objects")
            for field in ("name", "unit", "definition"):
                _string(measurement.get(field), f"measurement {field}")
            if measurement["name"] in names:
                raise ValueError("Duplicate measurement name within a record")
            names.add(measurement["name"])
            status = measurement.get("status")
            if status not in STATUSES:
                raise ValueError("Unknown measurement status")
            value = measurement.get("value")
            if (status == "observed") != (value is not None):
                raise ValueError("Only observed measurements have a value")
            if status == "observed" and measurement["unit"] == "boolean" and type(value) is not bool:
                raise ValueError("Boolean measurement must be boolean")
            if status == "observed" and measurement["unit"] in {
                    "count", "turns", "operations", "cases", "tokens", "fraction"}:
                if type(value) not in (int, float):
                    raise ValueError("Numeric measurement must be numeric, not boolean")
            refs(measurement.get("evidence"))
        order = []
        for event in record["events"]:
            if not isinstance(event, dict):
                raise ValueError("Events must be objects")
            _string(event.get("kind"), "event kind")
            _string(event.get("at"), "event time", nullable=True)
            if type(event.get("sequence")) is not int or event["sequence"] < 0:
                raise ValueError("Event sequence must be a nonnegative integer")
            order.append(event["sequence"])
            if not isinstance(event.get("attributes"), dict):
                raise ValueError("Event attributes must be an object")
            refs(event.get("evidence"))
        if order != sorted(set(order)):
            raise ValueError("Event sequence must be unique and increasing within an episode")
    for relation in bundle["relations"]:
        if not isinstance(relation, dict):
            raise ValueError("Relations must be objects")
        if relation.get("source") not in record_ids or relation.get("target") not in record_ids:
            raise ValueError("Relation endpoints must be present records")
        _string(relation.get("kind"), "relation kind")
        if not isinstance(relation.get("attributes"), dict):
            raise ValueError("Relation attributes must be an object")
        refs(relation.get("evidence"))
    return {"records": len(record_ids), "sources": len(source_ids),
            "events": sum(len(record["events"]) for record in bundle["records"]),
            "relations": len(bundle["relations"])}
