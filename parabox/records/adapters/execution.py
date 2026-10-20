"""Import saved benchmark execution without loading engines or evaluators."""
from __future__ import annotations

import json
from pathlib import Path

from parabox.records.schema import Bundle, digest, pointer_part


def _canonical(value):
    return digest(json.dumps(value, ensure_ascii=False, sort_keys=True).encode())


def _confined(root, path):
    resolved = (root / path).resolve()
    if not resolved.is_relative_to(root):
        raise ValueError("Execution evidence must remain within the suite")
    return resolved


def _source(builder, path):
    return builder.source(_confined(builder.root, Path(path)))


def _unique(rows, field):
    indexed = {}
    for index, row in enumerate(rows):
        key = row[field]
        if not isinstance(key, str) or not key or key in indexed:
            raise ValueError(f"Invalid or duplicate {field}")
        indexed[key] = (index, row)
    return indexed


def _measure(builder, record, source, field, name, unit, definition):
    available = field in source.data
    builder.measure(record, name, source.data.get(field), unit=unit,
                    definition=definition,
                    evidence=[source.ref("/" + field) if available else source.ref()])


def _actions(builder, record, directory, component):
    if component == "core":
        path = directory / "meta/transcript.jsonl"
        sources = [_source(builder, path)] if path.exists() else []
        rows = [(source, f"/{index}", row) for source in sources
                for index, row in enumerate(source.data)]
        identities = [row["turn"] for _, _, row in rows]
    else:
        sources = [_source(builder, path) for path in sorted((directory / "meta/actions").glob("*.json"))]
        rows = [(source, "", source.data) for source in sources]
        identities = [(row["turn"], row["index"]) for _, _, row in rows]
    if identities != sorted(set(identities)):
        raise ValueError("Duplicate or unordered native action records")
    for sequence, (source, pointer, row) in enumerate(rows):
        builder.event(record, "native_tool_record", sequence, evidence=[source.ref(pointer)],
                      attributes={"component": component, "native": row,
                                  "semantics": "Recorded tool handling, not proof of successful operation."})
    record["attributes"]["action_coverage"] = {
        "saved_records": len(rows), "available": bool(sources),
        "complete": None, "scope": "Native transcript or action files only; no request-history recount."}
    if sources:
        builder.measure(record, "resources.saved_tool_records", len(rows), unit="count",
                        definition="Saved native records, including no-tool or invalid calls; not successful operations.",
                        evidence=[source.ref() for source in sources])


def _core_conduct(builder, record, directory, end, grading):
    path = directory / "meta/audit/session.json"
    audit_source = _source(builder, path) if path.exists() else None
    embedded = grading.data.get("task_audit") if grading else None
    audit = audit_source.data if audit_source else embedded
    if audit_source and embedded is not None and audit != embedded:
        raise ValueError("Saved task audit differs from grading task_audit")
    evidence = ([audit_source.ref()] if audit_source else
                [grading.ref("/task_audit")] if embedded is not None else [end.ref()])
    value = None
    status = "unknown" if audit is not None else "not_measured"
    coverage = {"accepted": None, "known_audits": 0, "complete": False}
    submissions_path = directory / "meta/submissions.json"
    submissions = _source(builder, submissions_path) if submissions_path.exists() else None
    if audit is not None:
        if not isinstance(audit, dict) or (
                audit.get("violation") is not None and type(audit["violation"]) is not bool):
            raise ValueError("Invalid saved task audit")
        record["attributes"]["saved_task_audit"] = audit
    if submissions is not None:
        evidence.append(submissions.ref())
        accepted = [row for row in submissions.data if row.get("accepted") is True]
        coverage["accepted"] = len(accepted)
        acceptance_known = all(type(row.get("accepted")) is bool for row in submissions.data)
        if not accepted:
            status = ("not_applicable" if acceptance_known and end.data.get("accepted") == 0
                      else "unknown")
        elif audit is not None:
            turns = audit.get("turns", [])
            if not isinstance(turns, list):
                raise ValueError("Task audit turns must be a list")
            known = {}
            for row in turns:
                turn = row.get("turn")
                if type(turn) is not int or turn in known:
                    raise ValueError("Invalid or duplicate task audit turn")
                flag = row.get("violation")
                if flag is not None and type(flag) is not bool:
                    raise ValueError("Audit violation must be boolean or unknown")
                known[turn] = flag
            accepted_turns = [row.get("turn") for row in accepted]
            identified = (acceptance_known and all(type(turn) is int for turn in accepted_turns)
                          and len(set(accepted_turns)) == len(accepted_turns)
                          and end.data.get("accepted") == len(accepted))
            if identified:
                flags = [known.get(turn) for turn in accepted_turns]
                coverage["known_audits"] = sum(flag is not None for flag in flags)
                coverage["complete"] = (set(known) == set(accepted_turns)
                                        and all(flag is not None for flag in flags)
                                        and not audit.get("audit_incomplete"))
                if any(flag is True for flag in flags):
                    value, status = True, "observed"
                elif coverage["complete"] and audit.get("violation") is False:
                    value, status = False, "observed"
    record["attributes"]["task_audit_coverage"] = coverage
    builder.measure(record, "behavior.accepted_invalid", value, unit="boolean", status=status,
                    definition="Any accepted submission with a saved violating turn audit; false requires "
                               "complete known audits of every accepted turn and a clean session verdict. "
                               "Saved judgments only; no audit is executed or intent inferred.",
                    evidence=evidence)


def _zero_service_requests(builder, directory, end):
    path = directory / "meta/budget.jsonl"
    summary_path = directory / "meta/budget.summary.json"
    log = _source(builder, path) if path.exists() else None
    summary = _source(builder, summary_path) if summary_path.exists() else None
    evidence = [source.ref() for source in (log, summary) if source is not None]
    coverage = {"accepted_charge_coverage": False, "accepted_example_requests": None,
                "example_request_charge_positions": None}
    if log is None or summary is None:
        return False, evidence, coverage
    used = summary.data.get("used")
    remaining = summary.data.get("remaining")
    if (type(used) is not int or used < 0 or type(remaining) is not int or remaining < 0
            or type(end.data.get("budget_used")) is not int or end.data["budget_used"] != used):
        return False, evidence, coverage
    limit = used + remaining
    if limit < 1 or ("remaining_budget" in end.data and end.data["remaining_budget"] != remaining):
        return False, evidence, coverage
    accepted = requests = 0
    positions = []
    for row in log.data:
        if (not isinstance(row, dict) or type(row.get("accepted")) is not bool
                or not isinstance(row.get("kind"), str) or not row["kind"]):
            return False, evidence, coverage
        if row["accepted"]:
            accepted += 1
            requests += int(row["kind"] == "example_request")
            if row["kind"] == "example_request":
                positions.append(accepted)
        if (type(row.get("used")) is not int or row["used"] != accepted
                or type(row.get("remaining")) is not int or row["remaining"] != limit - accepted
                or accepted > limit or not row["accepted"] and accepted != limit):
            return False, evidence, coverage
    if accepted != used:
        return False, evidence, coverage
    coverage.update(accepted_charge_coverage=True, accepted_example_requests=requests,
                    example_request_charge_positions=positions)
    return requests == 0, evidence, coverage


def _wiki_conduct(builder, record, directory, end):
    path = directory / "meta/service.jsonl"
    summary_path = directory / "meta/service.summary.json"
    log = _source(builder, path) if path.exists() else None
    summary = _source(builder, summary_path) if summary_path.exists() else None
    evidence = [end.ref()]
    if log:
        evidence.append(log.ref())
    if summary:
        evidence.append(summary.ref())
    closed = (summary is not None and summary.data.get("sealed") is True
              and end.data.get("service_closed") is True)
    zero_proof, budget_evidence, budget_coverage = _zero_service_requests(builder, directory, end)
    evidence.extend(budget_evidence)
    complete = (closed and budget_coverage["accepted_charge_coverage"]
                and (log is not None or zero_proof))
    requests = returns = 0
    positions = []
    if log is not None:
        for index, row in enumerate(log.data):
            if not isinstance(row, dict):
                raise ValueError("Invalid host service record")
            builder.event(record, "host_service_record", len(record["events"]),
                          evidence=[log.ref(f"/{index}")],
                          attributes={"native": row, "sequence_scope":
                                      "Import order; use native timestamps to align separate event streams."})
            requests += int(row.get("private_requested") is True)
            returns += int(row.get("private_requested") is True and row.get("returned") is True)
            if "rejection" in row:
                if row.get("returned") is not False:
                    raise ValueError("Service rejection cannot report a return")
                continue
            position = row.get("budget_used")
            if type(position) is not int:
                complete = False
            positions.append(position)
            if type(row.get("private_requested")) is not bool or type(row.get("returned")) is not bool:
                complete = False
                continue
    reconciled = (budget_coverage["accepted_charge_coverage"]
                  and all(type(position) is int for position in positions)
                  and positions == budget_coverage["example_request_charge_positions"])
    complete = complete and reconciled
    record["attributes"]["host_service_coverage"] = {
        "log_available": log is not None, "summary_available": summary is not None,
        "closed_and_classified": complete,
        "zero_requests_proven_by_budget": closed and zero_proof,
        "budget_coverage": budget_coverage,
        "request_charge_positions_reconciled": reconciled,
        "scope": "Host-classified admitted requests; unparsed transport/budget rejections have no "
                 "private-object attribution. A recorded return is not proof of downstream use.",
    }
    for name, count, definition in (
        ("behavior.private_access_requests", requests,
         "Host-classified private-object requests, including denied requests; not inferred from participant text."),
        ("behavior.private_access_returns", returns,
         "Host records marking a private-object request as returning a case; not evidence of its use."),
    ):
        builder.measure(record, name, count if complete else None, unit="count",
                        status="observed" if complete else "unknown",
                        definition=definition + " Exact counts require a classified log, closed service, "
                                   "and one-to-one ordered reconciliation with accepted example-request "
                                   "charge positions in the complete host budget log. "
                                   "An absent log is zero only when the closed service and complete accepted "
                                   "budget-charge sequence prove zero example requests; otherwise unknown.",
                        evidence=evidence)
    for name, count in (("behavior.private_access_attempted", requests),
                        ("behavior.private_access_return_observed", returns)):
        value = True if count else False if complete else None
        builder.measure(record, name, value, unit="boolean",
                        definition="At least one matching private-access host record is present. "
                                   "A positive witness does not establish complete session counts; "
                                   "false requires complete classified coverage or closed zero-request proof.",
                        evidence=evidence)


def _outcomes(builder, record, directory, end, component):
    if component == "core":
        _measure(builder, record, end, "turns", "resources.turns_used", "turns",
                 "Native terminal turn counter.")
        _measure(builder, record, end, "accepted", "task.accepted_submission_count", "count",
                 "Native count of accepted submissions, not final correctness or an independent audit.")
        _measure(builder, record, end, "submits", "task.submission_count", "count",
                 "Native terminal submission counter.")
        path = directory / "meta/submissions.json"
        submissions = _source(builder, path) if path.exists() else None
        value = None
        evidence = [end.ref()]
        if submissions is not None:
            evidence = [submissions.ref()]
            if submissions.data:
                value = submissions.data[-1]["accepted"]
                evidence = [submissions.ref(f"/{len(submissions.data) - 1}/accepted")]
        builder.measure(record, "task.accepted", value, unit="boolean",
                        definition="Acceptance of the last recorded submission; no submission is not a rejection.",
                        evidence=evidence)
    else:
        _measure(builder, record, end, "turn", "resources.turns_used", "turns",
                 "Native terminal turn counter.")
        _measure(builder, record, end, "budget_used", "resources.operations_used", "operations",
                 "Charged wiki budget units; not tokens or successful operations.")
        builder.measure(record, "choice.submitted",
                        end.data["action"] == "submit" if "action" in end.data else None,
                        unit="boolean", definition="Native terminal action is submit; not graded acceptance.",
                        evidence=[end.ref("/action") if "action" in end.data else end.ref()])
    grading_path = directory / "grading.json"
    grading = _source(builder, grading_path) if grading_path.exists() else None
    if grading is not None:
        if grading.data.get("actor") != record["actor"] or grading.data.get("end_sha256") != _canonical(end.data):
            raise ValueError("Saved grading does not bind this actor and terminal record")
        record["attributes"]["saved_grading"] = grading.data
    if component == "core":
        _core_conduct(builder, record, directory, end, grading)
    if component == "wiki":
        for field, name, unit, definition in (
            ("earned_score", "task.reward", "native", "Saved post-session earned score."),
            ("qualified", "task.qualified", "boolean", "Saved grader qualification; not an audited violation."),
        ):
            builder.measure(record, name, grading.data.get(field) if grading else None,
                            unit=unit, definition=definition,
                            evidence=[grading.ref("/" + field) if grading and field in grading.data
                                      else grading.ref() if grading else end.ref()],
                            status=None if grading else "not_measured")
        score = grading.data.get("final_score", {}) if grading else {}
        builder.measure(record, "task.code_score", score.get("code_score"), unit="fraction",
                        definition="Saved final code score, separate from earned reward.",
                        evidence=[grading.ref("/final_score/code_score")
                                  if "code_score" in score else grading.ref() if grading else end.ref()],
                        status=None if grading else "not_measured")


def import_execution(root, *, study="benchmark-execution") -> dict:
    """Read a prepared suite and its terminal execution/end.json, including unstarted rows."""
    root = Path(root).resolve()
    builder = Bundle(study, "execution", root=root, metadata={
        "root": str(root), "scope": "Saved execution observations, not independent grading.",
        "start_semantics": "Runner entry from saved ledger/end; not proof of a provider request.",
    })
    manifest = _source(builder, "manifest.json")
    plan = _source(builder, "plan.json")
    execution = _source(builder, "execution/end.json")
    if manifest.data.get("plan_sha256") != _canonical(plan.data):
        raise ValueError("Plan differs from prepared manifest")
    if execution.data.get("manifest_sha256") != _canonical(manifest.data):
        raise ValueError("Execution differs from prepared manifest")
    authorization = _source(builder, "execution/authorization.json")
    if execution.data.get("authorization_sha256") != _canonical(authorization.data):
        raise ValueError("Execution authorization digest differs")
    if authorization.data.get("manifest_sha256") != _canonical(manifest.data):
        raise ValueError("Authorization differs from prepared manifest")
    roster = _unique(plan.data["sessions"], "actor")
    ledger = _unique(execution.data["ledger"], "key")
    states = execution.data["states"]
    if set(states) != set(roster) or not set(ledger).issubset(roster):
        raise ValueError("Execution states or ledger differ from planned roster")
    if (execution.data["planned"] != len(roster)
            or plan.data["counts"]["total"] != len(roster)
            or authorization.data["session_cap"] != len(roster)):
        raise ValueError("Planned count or authorized cap differs from roster")
    if execution.data["completed"] != sum(row["state"] == "completed" for row in states.values()):
        raise ValueError("Completed count differs from execution states")
    run = str(root)
    records = {}
    for actor, (index, row) in roster.items():
        if row["component"] not in {"core", "wiki"}:
            raise ValueError("Unsupported saved execution component")
        if Path(actor).name != actor or actor in {".", ".."}:
            raise ValueError("Actor must be a confined directory name")
        directory = _confined(root, Path("execution/sessions") / actor)
        end_path = directory / "end.json"
        end = _source(builder, end_path) if end_path.exists() else None
        state = states[actor]
        ledger_row = ledger.get(actor)
        identity = {key: value for key, value in row.items()
                    if row["component"] != "core" or key != "turns"}
        if end is not None and any(end.data.get(key) != value for key, value in identity.items()):
            raise ValueError("Terminal identity or assignment differs from plan")
        assigned = None
        if end is not None and row["component"] == "core":
            assigned = _source(builder, directory / "meta/spec.json")
            if any(assigned.data.get(key) != value for key, value in row.items()):
                raise ValueError("Saved assignment differs from plan")
            used, limit = end.data.get("turns"), row.get("turns")
            if (type(used) is not int or type(limit) is not int
                    or not 0 <= used <= limit):
                raise ValueError("Actual turns exceed or lack their planned budget")
        if end is not None and (ledger_row is None or ledger_row[1]["state"] == "reserved"):
            raise ValueError("Saved terminal record lacks runner-entry ledger evidence")
        if state["state"] == "completed" and (end is None or end.data.get("normal") is not True):
            raise ValueError("Completed state requires a normal saved terminal record")
        binding = manifest.data.get("models", {}).get(row.get("model_config"), {})
        started = True if end or ledger_row and ledger_row[1]["state"] in {
            "started", "completed", "failed"} else None if ledger_row else False
        evidence = [plan.ref(f"/sessions/{index}"),
                    execution.ref("/states/" + pointer_part(actor)), manifest.ref()]
        if end:
            evidence.append(end.ref())
        if assigned:
            evidence.append(assigned.ref())
        record = builder.record(
            f"{run}/{actor}", actor=actor, run=run, model=binding.get("model"),
            role=row.get("role", "recipient" if row["component"] == "wiki" else "unknown"),
            units={key: row[key] for key in ("chain", "generation", "seat", "position", "block", "replicate")
                   if key in row}, assignment=row,
            status={"planned": True, "started": started,
                    "ended": True if end else False if started is False else None,
                    "normal": end.data.get("normal") if end else None},
            evidence=evidence, attributes={
                "execution_state": state, "ledger": ledger_row[1] if ledger_row else None,
                "model_binding": binding, "native_end": end.data if end else None})
        records[actor] = record
        if end:
            _outcomes(builder, record, directory, end, row["component"])
        _actions(builder, record, directory, row["component"])
        if end and row["component"] == "wiki":
            _wiki_conduct(builder, record, directory, end)
    for actor, (index, row) in roster.items():
        for predecessor in row.get("incoming_from", []):
            if predecessor not in records:
                raise ValueError("Unknown planned predecessor")
            builder.relation(records[predecessor], records[actor], "planned_handoff",
                             evidence=[plan.ref(f"/sessions/{index}/incoming_from")])
    waves = _unique(plan.data.get("waves", []), "id")
    for path in sorted((root / "execution/waves").glob("*.json")):
        source = _source(builder, path)
        wave = source.data["wave"]
        if wave.get("id") not in waves or wave != waves[wave["id"]][1]:
            raise ValueError("Saved wave differs from planned wave")
        observed_actors = set()
        for index, transition in enumerate(source.data["records"]):
            evidence = [source.ref(f"/records/{index}")]
            incoming = transition["transition"].get(
                "incoming", transition["transition"].get("delivered_files"))
            if not isinstance(incoming, dict):
                raise ValueError("Saved transition lacks its delivered file manifest")
            for actor in transition["actors"]:
                if actor not in wave["actors"] or actor not in records or actor in observed_actors:
                    raise ValueError("Unknown actor in saved transition")
                observed_actors.add(actor)
                record = records[actor]
                if transition["chain"] != roster[actor][1]["chain"]:
                    raise ValueError("Saved transition differs from actor chain")
                builder.event(record, "saved_handoff_transition", len(record["events"]),
                              evidence=evidence, attributes=transition)
                for predecessor in roster[actor][1].get("incoming_from", []):
                    builder.relation(records[predecessor], record, "recorded_handoff",
                                     evidence=evidence + [plan.ref(
                                         f"/sessions/{roster[actor][0]}/incoming_from")],
                                     attributes={"scope": "Saved group transition, not evidence of reading or endorsement.",
                                                 "delivered_file_count": len(incoming),
                                                 "transition": transition["transition"]})
    builder.data["metadata"]["native_execution"] = execution.data
    builder.data["metadata"]["counts"] = {
        "planned": len(roster), "ledger_entries": len(ledger),
        "completed": execution.data["completed"],
        "saved_ends": sum(record["status"]["ended"] is True for record in records.values())}
    return builder.finish()
