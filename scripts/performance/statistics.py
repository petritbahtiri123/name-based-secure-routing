from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Sequence


@dataclass(frozen=True)
class Cell:
    environment_digest: str
    topology: str
    build_profile: str
    payload_bytes: int
    load_level: str
    connection_lifecycle: str
    run_ordinal: int
    implementation: str
    scenario: str

    def match_key(self) -> tuple[object, ...]:
        return (
            self.environment_digest,
            self.topology,
            self.build_profile,
            self.payload_bytes,
            self.load_level,
            self.connection_lifecycle,
            self.run_ordinal,
        )


def _nearest_rank(values: Sequence[int], quantile: float) -> int:
    return values[max(0, math.ceil(quantile * len(values)) - 1)]


def summarize(samples: Sequence[int]) -> dict[str, int | None]:
    if not samples:
        raise ValueError("at least one successful sample is required")
    values = sorted(samples)
    return {
        "count": len(values),
        "min": values[0],
        "max": values[-1],
        "p50": _nearest_rank(values, 0.50),
        "p95": _nearest_rank(values, 0.95),
        "p99": _nearest_rank(values, 0.99),
        "p99_9": _nearest_rank(values, 0.999) if len(values) >= 100_000 else None,
    }


def bootstrap_run_ci(
    run_statistics: Sequence[int],
    *,
    resamples: int = 10_000,
    seed: int = 75,
) -> dict[str, int | str]:
    if len(run_statistics) < 5:
        raise ValueError("bootstrap confidence interval requires at least five independent runs")
    if resamples < 100:
        raise ValueError("bootstrap requires at least 100 resamples")
    values = list(run_statistics)
    generator = random.Random(seed)
    estimates = sorted(round(sum(generator.choice(values) for _ in values) / len(values)) for _ in range(resamples))
    return {
        "method": "independent-run-bootstrap-mean-v1",
        "run_count": len(values),
        "resamples": resamples,
        "seed": seed,
        "estimate": round(sum(values) / len(values)),
        "lower": _nearest_rank(estimates, 0.025),
        "upper": _nearest_rank(estimates, 0.975),
    }


def matched_overhead(nbsr: Cell, direct: Cell, nbsr_ns: int, direct_ns: int) -> int:
    if nbsr.match_key() != direct.match_key():
        raise ValueError("unmatched benchmark cells")
    pairs = {
        ("nbsr-cold", "direct-cold", "cold"),
        ("nbsr-warm-new-service", "direct-warm", "warm"),
        ("nbsr-warm-existing-service", "direct-warm", "warm"),
    }
    if (nbsr.scenario, direct.scenario, nbsr.connection_lifecycle) not in pairs:
        raise ValueError("invalid overhead scenario pair")
    if nbsr.implementation not in {"rust-rust", "go-rust"} or direct.implementation != "direct-quic":
        raise ValueError("invalid overhead implementation pair")
    return nbsr_ns - direct_ns
