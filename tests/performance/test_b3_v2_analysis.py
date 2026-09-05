import pytest

from scripts.performance.b3_v2_analysis import analyze_cycles, analyze_scale


def fixture():
    return {"name": "cycles", "cycles": 5,
            "cleanup": {"all_zero": True, "source_cycle_all_zero": True},
            "samples": [{"role": role, "phase": "cooldown", "cycle": i,
                         "private_bytes": 1000 + i * 100, "working_set_bytes": 2000 + i * 100,
                         "handle_count": 10, "thread_count": 4, "process_count": 1}
                        for role in ("source", "destination") for i in range(5)]}


def test_retained_private_growth_does_not_prove_live_resource_growth_or_leak():
    result = analyze_cycles(fixture())
    assert result["ownership"] == "CLEAN"
    assert result["memory_cause"] == "INCONCLUSIVE"
    assert result["roles"]["source"]["private_slope_bytes_per_cycle"] == 100


def test_missing_last_source_cooldown_is_rejected():
    cell = fixture()
    cell["samples"] = [x for x in cell["samples"] if not (x["role"] == "source" and x["cycle"] == 4)]
    with pytest.raises(ValueError, match="cooldown"):
        analyze_cycles(cell)


def test_nonzero_ownership_cannot_be_clean():
    cell = fixture()
    cell["cleanup"]["all_zero"] = False
    assert analyze_cycles(cell)["ownership"] == "RESOURCE_GROWTH"


def test_scale_refuses_to_pool_registry_and_materialized_residency():
    cells = [{"name": str(mode), "kind": "streams", "materialized_streams": mode,
              "active_count": 16, "cleanup": {"all_zero": True}, "resource_scope": "streams",
              "samples": [{"role": role, "phase": phase, "private_bytes": 1000,
                           "working_set_bytes": 1000, "handle_count": 10, "thread_count": 4}
                          for role in ("source", "destination") for phase in ("idle", "active")]}
             for mode in (False, True)]
    with pytest.raises(ValueError, match="residency"):
        analyze_scale(cells)


def test_missing_ownership_is_unknown_not_measured_growth():
    cell = fixture()
    del cell["cleanup"]["source_cycle_all_zero"]
    with pytest.raises(ValueError, match="ownership"):
        analyze_cycles(cell)


def test_scale_preserves_coupled_scope_and_requires_five_dispersed_repeats():
    cells = []
    for repeat, amount in enumerate((1000, 2000, 3000)):
        cells.append({"name": str(repeat), "kind": "sessions", "active_count": 16,
                      "resource_scope": "connection/session/channel/stream bundle",
                      "cleanup": {"all_zero": True}, "samples": [
                          {"role": role, "phase": phase, "private_bytes": amount if phase == "active" else 100,
                           "working_set_bytes": amount, "handle_count": 10, "thread_count": 4}
                          for role in ("source", "destination") for phase in ("idle", "active")]})
    row = analyze_scale(cells)[0]
    assert row["resource_scope"] == "connection/session/channel/stream bundle"
    assert not row["points"][0]["repeat_gate"]
    assert row["derived_active_private_slope_bytes_per_unit"] is None
    cells[0]["cleanup"]["all_zero"] = False
    with pytest.raises(ValueError, match="failed cleanup"):
        analyze_scale(cells)
