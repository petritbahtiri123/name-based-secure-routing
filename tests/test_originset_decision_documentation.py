from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DECISION = ROOT / "docs" / "protocol" / "originset-compatibility-authority-decision.md"
V36_DECISIONS = ROOT / "docs" / "protocol" / "v3.6-decisions.md"
ROADMAP = ROOT / "docs" / "superpowers" / "plans" / "2026-07-28-v3.6-protocol-roadmap.md"


def _normalized(path: Path) -> str:
    return " ".join(path.read_text(encoding="utf-8").split())


def test_originset_decision_is_approved_but_runtime_remains_gated() -> None:
    text = _normalized(DECISION)

    assert "**Decision ID:** D7" in text
    assert "**Status:** Approved" in text
    assert "D7-1 through D7-5 were approved" in text
    assert "Phase C may implement and test" in text
    assert "runtime integration remain unauthorized" in text


def test_originset_placement_preserves_core_v01_and_defers_native_wire() -> None:
    text = _normalized(DECISION)

    for rule in (
        "Derived OriginSet is an internal WP2/WP3 model",
        "not serialized",
        "not a Core v0.1 extension",
        "NBSR-native OriginSet is a Core v0.2 candidate",
        "no new numeric key",
        "no new message code",
        "no new error code",
        "no new state or transition",
        "no new Core v0.1 COSE wrapper",
    ):
        assert rule.casefold() in text.casefold()


def test_originset_authority_is_mode_specific_and_never_comes_from_reachability() -> None:
    text = _normalized(DECISION)

    for rule in (
        "LEGACY_DNS",
        "local derivation authority",
        "DNSSEC",
        "Web PKI",
        "HYBRID",
        "caller-supplied trust context",
        "NBSR_NATIVE",
        "ServiceRecord owner",
        "explicit delegation",
        "Destination Edge",
        "connector",
        "reachability does not confer publication authority",
    ):
        assert rule.casefold() in text.casefold()


def test_originset_publication_mode_policy_mapping_is_explicit() -> None:
    text = DECISION.read_text(encoding="utf-8")

    expected_rows = (
        "| `legacy` | `LEGACY_DNS` |",
        "| `dual-published` | `LEGACY_DNS`, `HYBRID`, or `NBSR_NATIVE` |",
        "| `nbsr-preferred` | `HYBRID` or `NBSR_NATIVE`; constrained legacy fallback remains separately gated |",
        "| `nbsr-secure-only` | `NBSR_NATIVE` only |",
    )
    for row in expected_rows:
        assert row in text
    assert "policy value is not a wire alias for the observed lifecycle mode" in text


def test_originset_rollback_equivocation_and_tombstone_rules_fail_closed() -> None:
    text = _normalized(DECISION)

    for rule in (
        "same sequence and same deterministic digest is idempotent",
        "same sequence and different digest is equivocation",
        "lower generation or sequence is rejected",
        "highest accepted generation",
        "tombstone",
        "cannot resurrect",
        "fail closed",
    ):
        assert rule.casefold() in text.casefold()


def test_originset_wrapper_direction_does_not_allocate_wire_details() -> None:
    text = _normalized(DECISION)

    assert "Approved future Core v0.2 wrapper direction" in text
    assert "COSE Sign1" in text
    assert "not part of D1-D6" in text
    assert "exact payload keys, message code, `kid` binding, and vectors require separate approval" in text


def test_v36_record_and_roadmap_point_to_phase_c_review() -> None:
    decisions = _normalized(V36_DECISIONS)
    roadmap = _normalized(ROADMAP)

    assert "D7 approved" in decisions
    assert "D7-1 through D7-5 were approved" in decisions
    assert "Phase C internal OriginSet model review" in decisions
    assert "Phase B complete" in roadmap
    assert "Service Channel modeling is deferred" in roadmap
