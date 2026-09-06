import io
import json

import pytest

from scripts.performance.b5_stream import B5Stream


class Sampler:
    def __init__(self):
        self.running = True
        self.calls = []

    def check_health(self, *, require_running=False):
        self.calls.append(require_running)
        if require_running and not self.running:
            raise RuntimeError("sampler stopped")


def records():
    counters = dict(offered=0, reserved=0, issued=0, completed=0, missed=0, unreserved_current=0)
    groups = [dict(group_id=0, **counters)]
    progress = dict(schema="nbsr-b5-grouped-progress-v1", event="b5_grouped_progress",
                    window_index=1, phase="steady", elapsed_ns=1_000_000_000,
                    interval_start_ns=0, interval_end_ns=1_000_000_000,
                    issue_deadline_ns=1_000_000_000, **counters, group_counters=groups,
                    goodput_bytes_per_second=0, sample_count=0, sample_stride=64,
                    sample_capacity=8, sample_overflow_count=0, p50_latency_ns=None,
                    p95_latency_ns=None, p99_latency_ns=None, max_reservation_lateness_ns=0,
                    errors=0, timeouts=0, evidence_valid=True)
    final = dict(schema="nbsr-b5-grouped-final-v1", groups=1, payload_bytes=1024,
                 streams_per_group=1, outstanding_per_stream=1, measurement_duration_ns=1_000_000_000,
                 drain_duration_ns=0, **counters, group_counters=groups, max_outstanding_observed=0,
                 errors=0, timeouts=0, collector_overflow_count=0, all_groups_joined=True,
                 source_cleanup={"status": "NOT_MEASURED"}, evidence_valid=True)
    return progress, final


def wire(record):
    return (json.dumps(record) + "\n").encode()


def setup(**kwargs):
    raw = io.BytesIO()
    sampler = Sampler()
    now = [0]
    options = dict(raw_sink=raw, groups=1, payload_bytes=1024, sampler=sampler,
                   deadline_ns=10, max_line_bytes=4096, max_lines=8, clock=lambda: now[0])
    options.update(kwargs)
    return B5Stream(**options), raw, sampler, now


def test_fragmented_stream_preserves_exact_bytes_and_requires_final_and_exit():
    stream, raw, sampler, _ = setup()
    progress, final = records()
    data = wire(progress) + wire(final)
    for offset in range(0, len(data), 17):
        stream.feed(data[offset:offset + 17])
    assert stream.finish(0) == final
    assert raw.getvalue() == data
    assert sampler.calls[:-1] and all(sampler.calls[:-1])
    assert sampler.calls[-1] is False  # finish follows source exit.
    assert stream.pending_bytes == 0


@pytest.mark.parametrize("suffix", [b"{}\n", b"\n", wire(records()[1])])
def test_any_record_after_final_fails_and_retains_raw_suffix(suffix):
    stream, raw, _, _ = setup()
    progress, final = records()
    data = wire(progress) + wire(final) + suffix
    with pytest.raises(ValueError):
        stream.feed(data)
    assert raw.getvalue() == data
    with pytest.raises(ValueError):
        stream.finish(0)


@pytest.mark.parametrize("case", ["missing", "partial", "exit", "counter", "duplicate_json"])
def test_missing_partial_failed_or_invalid_output_fails_closed(case):
    stream, raw, _, _ = setup()
    progress, final = records()
    data = wire(progress)
    if case == "partial":
        data += wire(final)[:-1]
    elif case == "exit":
        data += wire(final)
    elif case == "counter":
        progress["completed"] = 1
        data = wire(progress)
    elif case == "duplicate_json":
        data = b'{"event":"diagnostic","event":"diagnostic"}\n'
    with pytest.raises(ValueError):
        stream.feed(data)
        stream.finish(1 if case == "exit" else 0)
    assert raw.getvalue() == data


@pytest.mark.parametrize("limit", ["line", "count"])
def test_line_and_count_bounds_retain_partial_evidence(limit):
    stream, raw, _, _ = setup(max_line_bytes=32, max_lines=1)
    data = b"x" * 33 if limit == "line" else b'{"event":"diagnostic"}\n' * 2
    with pytest.raises(ValueError):
        stream.feed(data)
    assert raw.getvalue() == data
    assert stream.pending_bytes <= 32


@pytest.mark.parametrize("cause", ["deadline", "sampler"])
def test_silent_activity_requires_live_sampler_and_deadline_poll(cause):
    stream, _, sampler, now = setup()
    if cause == "deadline":
        now[0] = 10
    else:
        sampler.running = False
    with pytest.raises(ValueError):
        stream.check(source_active=True)
    with pytest.raises(ValueError):
        stream.feed(b"{}\n")


def test_guard_callback_failure_preserves_raw_before_abort():
    def abort(_):
        raise RuntimeError("live drift")
    stream, raw, _, _ = setup(on_progress=abort)
    data = wire(records()[0])
    with pytest.raises(ValueError, match="live drift"):
        stream.feed(data)
    assert raw.getvalue() == data


def test_diagnostics_are_streamed_without_retained_history():
    observed = []
    stream, raw, _, _ = setup(on_diagnostic=lambda value: observed.append(value["event"]))
    for _ in range(3):
        stream.feed(b'{"event":"diagnostic"}\n')
    assert observed == ["diagnostic"] * 3
    assert stream.pending_bytes == 0
    assert len(raw.getvalue()) > 0


def test_unknown_b5_schema_cannot_hide_as_diagnostic():
    stream, raw, _, _ = setup()
    data = b'{"schema":"nbsr-b5-unknown-v2","event":"diagnostic"}\n'
    with pytest.raises(ValueError):
        stream.feed(data)
    assert raw.getvalue() == data


def test_raw_write_failure_latches_and_huge_line_does_not_accumulate():
    class Broken(io.BytesIO):
        def write(self, value):
            super().write(value[:3])
            raise OSError("disk failure")
    raw = Broken()
    stream, _, _, _ = setup(raw_sink=raw)
    with pytest.raises(ValueError, match="disk failure"):
        stream.feed(b"bad stdout\n")
    assert raw.getvalue() == b"bad"
    with pytest.raises(ValueError):
        stream.check()

    stream, raw, _, _ = setup(max_line_bytes=32)
    data = b"x" * 200_000
    with pytest.raises(ValueError):
        stream.feed(data)
    assert raw.getvalue() == data
    assert stream.pending_bytes == 0
