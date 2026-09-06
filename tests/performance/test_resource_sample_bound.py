"""A declared resource-history bound must invalidate rather than truncate."""

import pytest

from scripts.performance import resources


@pytest.mark.parametrize("limit", [0, -1, True, 1.5, "3"])
def test_invalid_sample_bounds_are_rejected(limit):
    with pytest.raises(ValueError, match="sample bound"):
        resources.ProcessResourceSampler({"source": 1}, assigned_logical_processors=1, max_records=limit)


def test_sample_bound_latches_failure_and_preserves_prefix(monkeypatch):
    sample = resources.ProcessResourceSample(1, 1, 1, 100, 100, 100, 1, 1)
    monkeypatch.setattr(resources, "sample_windows_process", lambda _pid: sample)
    streamed = []
    sampler = resources.ProcessResourceSampler(
        {"source": 1},
        interval_seconds=0.001,
        assigned_logical_processors=1,
        record_sink=streamed.append,
        max_records=3,
    )
    sampler.start()
    sampler._thread.join(timeout=5)
    assert not sampler._thread.is_alive()
    assert len(sampler._records) == len(streamed) == 3
    assert sampler._records == streamed
    with pytest.raises(RuntimeError, match="authoritative resource") as caught:
        sampler.check_health()
    assert "sample bound" in str(caught.value.__cause__)
    with pytest.raises(RuntimeError, match="authoritative resource"):
        sampler.stop()


def test_default_keeps_existing_sampler_contract():
    sampler = resources.ProcessResourceSampler({"source": 1}, assigned_logical_processors=1)
    assert sampler.max_records is None
    sampler.check_health()


def test_live_coverage_detects_exit_after_initial_sample(monkeypatch):
    calls = 0

    def sample(_pid):
        nonlocal calls
        calls += 1
        if calls > 1:
            raise ProcessLookupError("process exited")
        return resources.ProcessResourceSample(1, 1, 1, 100, 100, 100, 1, 1)

    monkeypatch.setattr(resources, "sample_windows_process", sample)
    sampler = resources.ProcessResourceSampler(
        {"source": 1},
        interval_seconds=0.001,
        assigned_logical_processors=1,
        max_records=3,
    )
    sampler.start()
    sampler._thread.join(timeout=5)
    assert not sampler._thread.is_alive()
    with pytest.raises(RuntimeError, match="authoritative resource sampling stopped"):
        sampler.check_health(require_running=True)
    # Preserve the accepted process-exit/stop behavior for existing callers.
    assert len(sampler.stop()) == 1


@pytest.mark.parametrize("initial_success", [False, True])
def test_process_lookup_failure_retains_role_and_original_cause(monkeypatch, initial_success):
    original = ProcessLookupError("synthetic process lookup")
    calls = 0

    def sample(pid):
        nonlocal calls
        calls += 1
        if initial_success and calls == 1:
            return resources.ProcessResourceSample(pid, 1, 1, 100, 100, 100, 1, 1)
        raise original

    monkeypatch.setattr(resources, "sample_windows_process", sample)
    sampler = resources.ProcessResourceSampler(
        {"destination_0": 4321}, interval_seconds=0.001, assigned_logical_processors=1,
    )
    sampler.start()
    sampler._thread.join(timeout=5)
    with pytest.raises(RuntimeError) as caught:
        sampler.check_health(require_running=True)
    assert caught.value.__cause__ is original
    assert any("destination_0" in note and "4321" in note
               for note in original.__notes__)
    if initial_success:
        assert len(sampler.stop()) == 1
    else:
        with pytest.raises(RuntimeError):
            sampler.stop()
