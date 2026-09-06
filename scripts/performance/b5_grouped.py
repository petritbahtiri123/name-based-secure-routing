"""Streaming grouped B5 accounting; stability and cleanup are separate gates."""

import math


COUNTERS = ("offered", "reserved", "issued", "completed", "missed", "unreserved_current")
TOTALS = COUNTERS[:-1]
QUANTILES = ("p50_latency_ns", "p95_latency_ns", "p99_latency_ns")
PROGRESS = {
    "schema",
    "event",
    "window_index",
    "phase",
    "elapsed_ns",
    "interval_start_ns",
    "issue_deadline_ns",
    "interval_end_ns",
    *COUNTERS,
    "group_counters",
    "goodput_bytes_per_second",
    "sample_count",
    "sample_stride",
    "sample_capacity",
    "sample_overflow_count",
    *QUANTILES,
    "max_reservation_lateness_ns",
    "errors",
    "timeouts",
    "evidence_valid",
}
FINAL = {
    "schema",
    "groups",
    "payload_bytes",
    "streams_per_group",
    "outstanding_per_stream",
    "measurement_duration_ns",
    "drain_duration_ns",
    *COUNTERS,
    "group_counters",
    "max_outstanding_observed",
    "errors",
    "timeouts",
    "collector_overflow_count",
    "all_groups_joined",
    "source_cleanup",
    "evidence_valid",
}


def integer(value, minimum=0):
    if type(value) is not int or not minimum <= value <= 2**64 - 1:
        raise ValueError("invalid integer counter")
    return value


def require(condition):
    if not condition:
        raise ValueError("invalid grouped progress accounting")


def counts(value):
    result = tuple(integer(value[key]) for key in COUNTERS)
    offered, reserved, issued, completed, missed, current = result
    require(offered == reserved + missed + current and reserved >= issued >= completed)
    return result


class ProgressValidator:
    def __init__(self, groups, payload_bytes):
        integer(groups, 1)
        integer(payload_bytes, 1)
        require(groups <= 4 and payload_bytes in (1024, 16384))
        self.groups, self.payload_bytes = groups, payload_bytes
        self._failed = self._finished = False
        self._index = self._end = 0
        self._phase = None
        self._issue_deadline = None
        self._counts = None
        self._group_counts = None
        self._sampling = None
        self._lateness = 0

    @property
    def retained_group_count(self):
        return len(self._group_counts) if self._group_counts is not None else 0

    @property
    def retained_window_count(self):
        return int(self._counts is not None)

    def _snapshot(self, value):
        aggregate = counts(value)
        rows = value["group_counters"]
        require(type(rows) is list and len(rows) == self.groups)
        result = [None] * self.groups
        for row in rows:
            require(type(row) is dict and set(row) == {"group_id", *COUNTERS})
            group = integer(row["group_id"])
            require(group < self.groups and result[group] is None)
            result[group] = counts(row)
        require(all(sum(row[index] for row in result) == aggregate[index] for index in range(len(COUNTERS))))
        return aggregate, tuple(result)

    def accept(self, record):
        try:
            require(not self._failed and not self._finished)
            require(type(record) is dict and set(record) == PROGRESS)
            require(record["schema"] == "nbsr-b5-grouped-progress-v1" and record["event"] == "b5_grouped_progress")
            index = integer(record["window_index"], 1)
            start, end = integer(record["interval_start_ns"]), integer(record["interval_end_ns"], 1)
            require(index == self._index + 1 and start == self._end and end > start)
            require(integer(record["elapsed_ns"]) == end)
            deadline = integer(record["issue_deadline_ns"], 1)
            require(self._issue_deadline is None or deadline == self._issue_deadline)
            phase = record["phase"]
            expected_phase = "steady" if end <= deadline else "drain" if start >= deadline else "mixed"
            require(phase == expected_phase)
            aggregate, groups = self._snapshot(record)
            if self._counts is not None:
                require(all(new >= old for new, old in zip(aggregate[:-1], self._counts[:-1])))
                require(all(all(new >= old for new, old in zip(row[:-1], prior[:-1])) for row, prior in zip(groups, self._group_counts)))
                if self._end >= deadline:
                    # Reservations stop at the issue deadline; issued writes may finish.
                    require(aggregate[:2] == self._counts[:2])
                    require(all(row[:2] == prior[:2] for row, prior in zip(groups, self._group_counts)))
            require(record["evidence_valid"] is True)
            require(all(integer(record[key]) == 0 for key in ("errors", "timeouts", "sample_overflow_count")))
            sample_count = integer(record["sample_count"])
            stride, capacity = integer(record["sample_stride"], 1), integer(record["sample_capacity"], 1)
            require(sample_count <= capacity)
            require(self._sampling is None or self._sampling == (stride, capacity))
            prior_completed = self._counts[3] if self._counts else 0
            require(sample_count == aggregate[3] // stride - prior_completed // stride)
            if sample_count == 0:
                require(all(record[key] is None for key in QUANTILES))
            else:
                quantiles = tuple(integer(record[key]) for key in QUANTILES)
                require(quantiles[0] <= quantiles[1] <= quantiles[2])
                require(sample_count != 1 or quantiles[0] == quantiles[1] == quantiles[2])
            delta = aggregate[3] - (self._counts[3] if self._counts else 0)
            require(sample_count <= delta)
            goodput = record["goodput_bytes_per_second"]
            require(type(goodput) in (int, float) and math.isfinite(goodput) and goodput >= 0)
            expected = delta * 2 * self.payload_bytes * 1_000_000_000 / (end - start)
            # Counts are exact; only the serialized floating rate gets rounding tolerance.
            require(math.isclose(goodput, expected, rel_tol=1e-12, abs_tol=1e-9))
            lateness = integer(record["max_reservation_lateness_ns"])
            require(lateness >= self._lateness)
            self._issue_deadline = deadline
            self._index, self._end, self._phase = index, end, phase
            self._counts, self._group_counts = aggregate, groups
            self._sampling, self._lateness = (stride, capacity), lateness
        except (ValueError, TypeError, KeyError, OverflowError) as error:
            self._failed = True
            raise ValueError("grouped progress rejected") from error

    def finish(self, final):
        try:
            require(not self._failed and not self._finished and self._index > 0)
            require(type(final) is dict and set(final) == FINAL)
            require(final["schema"] == "nbsr-b5-grouped-final-v1")
            require(integer(final["groups"]) == self.groups and integer(final["payload_bytes"]) == self.payload_bytes)
            aggregate, groups = self._snapshot(final)
            require(aggregate == self._counts and groups == self._group_counts)
            measurement = integer(final["measurement_duration_ns"], 1)
            drain = integer(final["drain_duration_ns"])
            require(measurement + drain == self._end)
            require(measurement == self._issue_deadline and self._end >= measurement)
            require(aggregate[5] == 0 and aggregate[1] == aggregate[2] == aggregate[3])
            require(all(row[5] == 0 and row[1] == row[2] == row[3] for row in groups))
            streams, depth = integer(final["streams_per_group"], 1), integer(final["outstanding_per_stream"], 1)
            require(streams <= 64 and depth <= 64)
            require(integer(final["max_outstanding_observed"]) <= self.groups * streams * depth)
            require(all(integer(final[key]) == 0 for key in ("errors", "timeouts", "collector_overflow_count")))
            require(final["all_groups_joined"] is True and final["evidence_valid"] is True)
            require(type(final["source_cleanup"]) is dict)  # Caller owns cleanup validation.
            self._finished = True
        except (ValueError, TypeError, KeyError, OverflowError) as error:
            self._failed = True
            raise ValueError("grouped final rejected") from error
