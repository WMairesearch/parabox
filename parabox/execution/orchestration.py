"""Supported sequential and generation-barrier callers, without automatic retries."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from .artifacts import handoff, manifest
from .runtime import execute_invocation, validate_invocations


def _policy(engine, policy):
    supported = getattr(engine, "policies", None)
    if supported is not None and policy not in supported:
        raise ValueError("Engine does not support requested handoff policy")


def run_sequential(invocations, *, engine, ledger, initial):
    _policy(engine, "replace")
    invocations = list(invocations)
    validate_invocations(invocations)
    manifest(initial)
    files, outcomes, lineage = dict(initial), [], []
    for invocation in invocations:
        outcome = execute_invocation(engine, ledger, invocation, files)
        outcomes.append(outcome)
        files, transition = handoff(files, [outcome], policy="replace")
        lineage.append(transition)
    return {"outcomes": outcomes, "files": files, "lineage": lineage}


def run_population(generations, *, engine, ledger, initial,
                   policy="population_all", workers=1):
    if policy not in ("population_all", "population_accepted"):
        raise ValueError("Population requires an explicit population merge policy")
    _policy(engine, policy)
    if type(workers) is not int or workers < 1:
        raise ValueError("Positive worker count required")
    generations = [list(generation) for generation in generations]
    validate_invocations([invocation for generation in generations for invocation in generation])
    manifest(initial)
    files, outcomes, lineage = dict(initial), [], []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for generation in generations:
            futures = [pool.submit(execute_invocation, engine, ledger, invocation, files)
                       for invocation in generation]
            results = [future.result() for future in futures]
            files, transition = handoff(files, results, policy=policy)
            outcomes.extend(results)
            lineage.append(transition)
    return {"outcomes": outcomes, "files": files, "lineage": lineage}
