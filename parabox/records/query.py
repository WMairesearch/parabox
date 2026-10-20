"""Descriptive queries without pooling studies, roles or outcome definitions."""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from statistics import mean

from .schema import validate


def select(bundle: dict, *, kind: str | None = None, model: str | None = None,
           role: str | None = None, run: str | None = None,
           condition: str | None = None, actor: str | None = None,
           started: str | None = None) -> list[dict]:
    if started not in (None, "true", "false", "unknown"):
        raise ValueError("started must be true, false or unknown")
    start_value = {"true": True, "false": False, "unknown": None}.get(started)
    filters = {"kind": kind, "model": model, "role": role, "run": run, "actor": actor}
    return [record for record in bundle["records"]
            if all(value is None or record.get(key) == value for key, value in filters.items())
            and (started is None or record["status"].get("started") is start_value)
            and (condition is None or record["assignment"].get("condition") == condition)]


def summarize(bundle: dict, *, records: list[dict] | None = None) -> dict:
    validate(bundle)
    records = bundle["records"] if records is None else records
    originals = {record["id"]: record for record in bundle["records"]}
    selected_ids = set()
    for record in records:
        if not isinstance(record, dict) or record.get("id") not in originals:
            raise ValueError("Summary records must belong to the bundle")
        if record["id"] in selected_ids:
            raise ValueError("Duplicate summary record")
        if record != originals[record["id"]]:
            raise ValueError("Summary record differs from its bundle record")
        selected_ids.add(record["id"])
    groups = defaultdict(list)
    for record in records:
        identity = {"study": bundle["study"], "run": record["run"], "kind": record["kind"],
                    "role": record["role"], "model": record["model"],
                    "assignment": record["assignment"]}
        groups[json.dumps(identity, sort_keys=True, separators=(",", ":"))].append(record)
    result = []
    for encoded, members in sorted(groups.items()):
        definitions = {}
        for record in members:
            for item in record["measurements"]:
                key = (item["name"], item["unit"], item["definition"])
                definitions.setdefault(key, {})[record["id"]] = item
        measurements = []
        for (name, unit, definition), by_record in sorted(definitions.items()):
            statuses = Counter(by_record[record["id"]]["status"]
                               if record["id"] in by_record else "not_measured" for record in members)
            values = [item["value"] for item in by_record.values() if item["status"] == "observed"]
            stats = {"name": name, "unit": unit, "definition": definition,
                     "statuses": dict(statuses), "known": len(values), "records": len(members)}
            if unit == "boolean":
                stats.update(true=values.count(True), false=values.count(False))
            elif values and all(type(value) in (int, float) for value in values):
                stats.update(sum=sum(values), mean=mean(values), minimum=min(values), maximum=max(values))
            measurements.append(stats)
        unit_names = sorted({name for record in members for name in record["units"]})
        units = {}
        for name in unit_names:
            observed = [record["units"].get(name) for record in members]
            units[name] = {
                "distinct": len({json.dumps(value, sort_keys=True) for value in observed if value is not None}),
                "missing": sum(value is None for value in observed),
            }
        result.append({"group": json.loads(encoded), "records": len(members),
                       "units": units, "measurements": measurements,
                       "status_counts": {field: dict(Counter(
                           "unknown" if record["status"].get(field) is None else
                           str(record["status"][field]).lower() for record in members))
                           for field in ("planned", "started", "ended", "normal")}})
    return {"study": bundle["study"], "records": len(records), "groups": result,
            "interpretation": "Descriptive saved observations. Groups retain assignment, run, role and outcome "
                              "definition. Counts of records are not independent sample sizes. Missing values "
                              "are not zero, and no pooled safety score or causal estimate is computed."}
