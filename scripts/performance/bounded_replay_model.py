"""Deterministic P1C replay-candidate model; not production replay code."""

from __future__ import annotations

import argparse
import json
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable
from typing import Protocol

MAX_STREAM_ORDINAL = ((2**62 - 1) - 4) // 4


def _validate_stream_ordinal(stream_ordinal: int) -> None:
    if not 0 <= stream_ordinal <= MAX_STREAM_ORDINAL:
        raise ValueError("outside legal QUIC stream ordinal domain")


class ReplayModel(Protocol):
    @property
    def state_entries(self) -> int: ...

    def observe(self, stream_ordinal: int) -> bool: ...


@dataclass
class FullHistoryOracle:
    used: set[int] = field(default_factory=set)

    @property
    def state_entries(self) -> int:
        return len(self.used)

    def observe(self, stream_ordinal: int) -> bool:
        _validate_stream_ordinal(stream_ordinal)
        if stream_ordinal in self.used:
            return False
        self.used.add(stream_ordinal)
        return True


@dataclass
class StrictHighWater:
    high: int | None = None

    @property
    def state_entries(self) -> int:
        return int(self.high is not None)

    def observe(self, stream_ordinal: int) -> bool:
        _validate_stream_ordinal(stream_ordinal)
        if self.high is not None and stream_ordinal <= self.high:
            return False
        self.high = stream_ordinal
        return True


@dataclass
class SlidingWindow:
    width: int
    high: int | None = None
    used: set[int] = field(default_factory=set)

    def __post_init__(self) -> None:
        if self.width <= 0:
            raise ValueError("window width must be positive")

    @property
    def state_entries(self) -> int:
        return len(self.used)

    def observe(self, stream_ordinal: int) -> bool:
        _validate_stream_ordinal(stream_ordinal)
        if self.high is None or stream_ordinal > self.high:
            self.high = stream_ordinal
            lower = self.high - self.width + 1
            self.used = {value for value in self.used if value >= lower}
            self.used.add(stream_ordinal)
            return True
        if stream_ordinal < self.high - self.width + 1:
            return False
        if stream_ordinal in self.used:
            return False
        self.used.add(stream_ordinal)
        return True


def compare_candidate(sequence: list[int], candidate: ReplayModel) -> dict[str, int]:
    oracle = FullHistoryOracle()
    false_accepts = 0
    false_rejects = 0
    maximum_state_entries = candidate.state_entries
    for stream_ordinal in sequence:
        expected = oracle.observe(stream_ordinal)
        actual = candidate.observe(stream_ordinal)
        false_accepts += int(actual and not expected)
        false_rejects += int(expected and not actual)
        maximum_state_entries = max(maximum_state_entries, candidate.state_entries)
    return {
        "events": len(sequence),
        "false_accepts": false_accepts,
        "false_rejects": false_rejects,
        "maximum_state_entries": maximum_state_entries,
    }


def _compare_many(
    sequences: list[list[int]], factory: Callable[[], ReplayModel]
) -> dict[str, int]:
    totals = {"false_accepts": 0, "false_rejects": 0, "maximum_state_entries": 0}
    for sequence in sequences:
        result = compare_candidate(sequence, factory())
        totals["false_accepts"] += result["false_accepts"]
        totals["false_rejects"] += result["false_rejects"]
        totals["maximum_state_entries"] = max(
            totals["maximum_state_entries"], result["maximum_state_entries"]
        )
    return totals


def run_investigation() -> dict[str, object]:
    seed = 0x503143
    generator = random.Random(seed)
    sequences: list[list[int]] = []
    for _ in range(10_000):
        distinct = generator.sample(range(0, 1 << 20), 64)
        duplicates = [distinct[index] for index in generator.sample(range(64), 16)]
        sequence = distinct + duplicates
        generator.shuffle(sequence)
        sequences.append(sequence)

    windows = (1, 4, 16, 64, 1_024)
    return {
        "model": "committed STREAM_OPEN QUIC stream ordinals",
        "seed": seed,
        "generated_sequences": len(sequences),
        "generated_events": sum(map(len, sequences)),
        "oracle": _compare_many(sequences, FullHistoryOracle),
        "strict_high_water": _compare_many(sequences, StrictHighWater),
        "sliding_windows": [
            {
                "window_ordinals": width,
                "bitmap_bits": width,
                "bitmap_payload_bytes": 8 + (width + 7) // 8,
                **_compare_many(sequences, lambda width=width: SlidingWindow(width)),
            }
            for width in windows
        ],
        "finite_window_counterexamples": [
            {
                "window_ordinals": width,
                "sequence": [0, width + 1, 1],
                **compare_candidate([0, width + 1, 1], SlidingWindow(width)),
            }
            for width in windows
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    rendered = json.dumps(run_investigation(), indent=2, sort_keys=True) + "\n"
    if args.output is None:
        print(rendered, end="")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
