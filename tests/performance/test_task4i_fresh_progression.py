import json

import pytest

from scripts import run_b4b_task4i as runner


def setup_fake(monkeypatch, tmp_path, values, invalid_at=None):
    binary = tmp_path / "binary"
    binary.write_bytes(b"synthetic")
    monkeypatch.setattr(runner.v2, "build", lambda target: {"source": binary})
    monkeypatch.setattr(runner.v2, "host_environment", lambda: {})
    calls = []

    def measured(*args, **kwargs):
        calls.append(kwargs)
        index = len(calls) - 1
        return dict(valid=index != invalid_at, requested_clients=512, started_clients=512,
                    connected_clients=512, successful_admissions=512, failed_admissions=0,
                    errors=0, timeouts=0, admission_rate=kwargs["release_rate"],
                    handshake_latency_ns={"50": 1, "95": 2, "99": 3},
                    admission_p50_latency_ns=1, admission_p95_latency_ns=2, admission_p99_latency_ns=3,
                    established_goodput_bytes_per_second=values[index % len(values)],
                    established_p99_latency_ns=4, effective_cores=1, peak_pending_clients=512,
                    cleanup={"all_zero": True, "processes_exited": True}, resources={"handles": 1})

    monkeypatch.setattr(runner.v2, "run_measured_cell", measured)
    return calls


@pytest.mark.parametrize("values,expected", [([100], 3), ([80, 100, 120, 100, 100], 5)])
def test_explicit_progression_preserves_shards_provenance_and_repeat_gate(monkeypatch, tmp_path, values, expected):
    calls = setup_fake(monkeypatch, tmp_path, values)
    output = tmp_path / "evidence"
    result = runner.execute(output, offered_rates=(25,), source_shards=2)
    assert len(calls) == expected
    assert all(call["source_shards"] == 2 and call["release_rate"] == 25 for call in calls)
    assert result["cells"][0]["valid"] == expected
    environment = json.loads((output / "environment.json").read_text())
    assert environment["source_shards"] == 2
    assert environment["offered_rates"] == [25]
    assert environment["total_clients"] == 512


@pytest.mark.parametrize("invalid_at,values", [(1, [100]), (4, [80, 100, 120, 100, 100])])
def test_invalid_attempt_cannot_qualify_a_cell_or_be_discarded(monkeypatch, tmp_path, invalid_at, values):
    setup_fake(monkeypatch, tmp_path, values, invalid_at=invalid_at)
    monkeypatch.setattr(runner, "RATES", (25,))
    output = tmp_path / "evidence"
    result = runner.execute(output)
    assert result["cells"] == []
    assert result["classification"] == "PARTIAL"
    assert result["invalid_runs"] == 1
    assert json.loads((output / f"raw/rate-25/r{invalid_at + 1}.json").read_text())["valid"] is False


def test_defaults_keep_existing_rates_and_one_shard(monkeypatch, tmp_path):
    calls = setup_fake(monkeypatch, tmp_path, [100])
    result = runner.execute(tmp_path / "evidence")
    assert [cell["offered_rate"] for cell in result["cells"]] == list(runner.RATES)
    assert all(call["source_shards"] == 1 for call in calls)
