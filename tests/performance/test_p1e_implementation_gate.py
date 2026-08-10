from pathlib import Path

from scripts.performance.p1e_implementation_gate import evaluate_repository


ROOT = Path(__file__).resolve().parents[2]


def test_repository_has_no_production_go_client_agent_owner() -> None:
    result = evaluate_repository(ROOT)
    assert result["go_modules"] == [
        "interop/nbsr-go-peer/go.mod",
        "verifiers/federation-go/go.mod",
    ]
    assert result["production_go_files"] == []
    assert result["wire_capable_go_owner"] == "interop_test_peer_only"


def test_current_go_routegrant_source_is_checked_in_fixture_not_acquisition() -> None:
    result = evaluate_repository(ROOT)
    assert result["go_route_grant_source"] == {
        "kind": "filesystem_fixture",
        "path_component": "route-open-body.cbor",
        "live_acquisition_api": False,
    }
    assert result["core_route_grant_acquisition_messages"] == []


def test_rust_cap_is_expressible_but_cannot_complete_coordinated_fix() -> None:
    result = evaluate_repository(ROOT)
    assert result["rust_hard_cap"] == {
        "insertion_point": "ChannelStreams.prepare_open",
        "typed_error": "StreamReject::OverCapacity",
        "wire_change_required": False,
    }
    assert result["partial_rust_only_fix_authorized"] is False


def test_gate_reports_exact_code_level_protocol_blocker() -> None:
    result = evaluate_repository(ROOT)
    assert result["outcome"] == "C"
    assert result["classification"] == "CODE_LEVEL_PROTOCOL_BLOCKED"
    assert result["production_implementation_authorized"] is False
    assert result["missing_contract"] == (
        "A production Go client/agent API and live fresh-RouteGrant acquisition "
        "contract for TS-B; the repository only supplies offline fixture bytes "
        "and Core v0.2 defines no acquisition exchange."
    )
