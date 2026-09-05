from scripts import run_b3_session_lifecycle as b3
from scripts import run_b3_v2 as v2
import pytest


def test_materialized_spec_is_explicit_and_separate():
    assert not v2.spec_for("channels", 2, 1).get("materialized_streams", False)
    spec = v2.spec_for("channels", 2, 1, materialized_streams=True)
    assert spec["materialized_streams"] is True
    assert spec["stream_residency"] == "materialized request and both endpoint handles"


def test_materialized_connection_only_workload_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="connection-only"):
        b3.run_cell("rust-rust", {**v2.spec_for("channels", 2, 1), "kind": "connections", "materialized_streams": True}, {}, tmp_path,
                    idle_seconds=0, active_seconds=0, cooldown_seconds=0, cadence=1)


def test_rust_scale_uses_one_source_process_not_process_per_session():
    assert b3.source_plan("rust-rust", 512, 1) == [(1, 0, 512)]
    assert b3.source_plan("rust-rust", 1, 50) == [(50, 0, 1)]
    assert b3.source_plan("go-rust", 2, 1) == [(1, 0, 1), (1, 1, 1)]
