"""Host-side execution guards that do not alter participant inputs or tools."""

from __future__ import annotations

from datetime import datetime, timezone


def utcnow():
    return datetime.now(timezone.utc)


def parse_deadline(value: str):
    deadline = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if deadline.tzinfo is None:
        raise ValueError("Deadline must be timezone-aware")
    return deadline


class DeadlineClient:
    def __init__(self, client, deadline: str, clock=utcnow):
        self.client, self.deadline, self.clock = client, parse_deadline(deadline), clock

    def complete(self, *args, **kwargs):
        if self.clock() >= self.deadline:
            raise TimeoutError("Execution deadline reached before model request")
        result = self.client.complete(*args, **kwargs)
        if self.clock() >= self.deadline:
            raise TimeoutError("Execution deadline reached before tool dispatch")
        return result


class BoundOutcomeEngine:
    def __init__(self, engine):
        self.engine = engine
        self.policies = engine.policies

    def __call__(self, invocation, incoming):
        outcome = self.engine(invocation, incoming)
        if outcome.end.get("actor") != invocation.spec["actor"]:
            raise ValueError("Outcome identity differs from the planned actor")
        return outcome
