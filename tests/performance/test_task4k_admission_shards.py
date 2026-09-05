from pathlib import Path

import pytest

from scripts.run_b4b_mixed_connections import lifecycle_client_command
from scripts.performance.resources import sample_windows_threads
from scripts.run_b4b_task4k import classify_boundary_movement


def command(shards: int = 1) -> list[str]:
    return lifecycle_client_command(
        Path("source.exe"),
        "127.0.0.1:4433",
        Path("authority"),
        Path("lifecycle"),
        connections=1,
        offset=0,
        logical_clients=512,
        release_rate=125,
        source_shards=shards,
    )


def test_default_single_shard_does_not_change_existing_command():
    assert "--lifecycle-source-shards" not in command(1)


def test_two_shards_is_explicitly_forwarded_to_source_driver():
    result = command(2)
    index = result.index("--lifecycle-source-shards")
    assert result[index + 1] == "2"


@pytest.mark.parametrize("invalid", [0, 3, 4])
def test_only_one_or_two_source_shards_are_accepted(invalid):
    with pytest.raises(ValueError, match="source shards"):
        command(invalid)


def test_windows_thread_sampler_reports_current_process_threads():
    import os

    samples = sample_windows_threads(os.getpid())
    assert samples
    assert all(sample.thread_id > 0 for sample in samples)
    assert all(sample.user_cpu_ns >= 0 and sample.kernel_cpu_ns >= 0 for sample in samples)


def test_pass_requires_two_shards_to_move_a_classification_boundary():
    one = [{"offered_rate": 125, "status": "STABLE"}, {"offered_rate": 150, "status": "DEGRADED"}]
    two = [{"offered_rate": 125, "status": "STABLE"}, {"offered_rate": 150, "status": "STABLE"}]
    assert classify_boundary_movement(one, two)["classification"] == "PASS"
    assert classify_boundary_movement(one, one)["classification"] == "FAIL"


def test_unclassified_baseline_is_not_a_proven_stable_boundary():
    cells = [{"offered_rate": 125, "status": "BASELINE"}, {"offered_rate": 150, "status": "DEGRADED"}]
    result = classify_boundary_movement(cells, cells)
    assert result["one_shard_highest_stable"] == 0
    assert result["classification"] == "FAIL"
