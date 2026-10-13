"""Block bootstrap. A block is resampled whole, so its arms stay paired."""
from __future__ import annotations

import random

BOOTSTRAP_SEED = 2026092612
DRAWS = 20_000


def rate(values) -> float | None:
    values = [bool(item) for item in values if item is not None]
    return None if not values else sum(values) / len(values)


def wilson(k: int, n: int, z: float = 1.96) -> dict | None:
    """95% Wilson score interval for a binomial proportion k/n."""
    if n <= 0:
        return None
    if k < 0 or k > n:
        raise ValueError(f"k={k} is outside 0..{n}")
    p = k / n
    z2 = z * z
    denom = 1 + z2 / n
    center = (p + z2 / (2 * n)) / denom
    margin = z * ((p * (1 - p) / n + z2 / (4 * n * n)) ** 0.5) / denom
    return {
        "k": k,
        "n": n,
        "rate": p,
        "low": max(0.0, center - margin),
        "high": min(1.0, center + margin),
    }


def bootstrap(units: list, fn, *, seed: int = BOOTSTRAP_SEED, draws: int = DRAWS) -> dict:
    if not units:
        return {"value": None, "draws": 0}
    value = fn(units)
    rng = random.Random(seed)
    samples = []
    skipped = 0
    width = len(units)
    for _ in range(draws):
        got = fn([units[rng.randrange(width)] for _ in range(width)])
        if got is None:
            skipped += 1
        else:
            samples.append(got)
    samples.sort()
    if not samples:
        return {"value": value, "draws": 0, "skipped": skipped}
    low = samples[int(0.025 * len(samples))]
    high = samples[min(len(samples) - 1, int(0.975 * len(samples)))]
    return {"value": value, "low": low, "high": high, "draws": len(samples), "skipped": skipped, "degenerate": low == high}
