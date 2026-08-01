from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STATUS = ROOT / "docs" / "protocol" / "status.md"
DECISION = ROOT / "docs" / "protocol" / "wp6-replicated-continuity-state-decision.md"
README = ROOT / "README.md"
ROADMAP = ROOT / "docs" / "superpowers" / "plans" / "2026-07-28-v3.6-protocol-roadmap.md"


def test_wp6_authoritative_docs_record_only_bounded_implemented_evidence() -> None:
    combined = " ".join(" ".join(path.read_text(encoding="utf-8").split()) for path in (STATUS, DECISION, README, ROADMAP))
    for required in (
        "WP6 is complete and evidence-closed at bounded deterministic prototype scope",
        "65 focused WP6 tests",
        "deterministic storage-neutral state machine",
        "simulated multi-replica",
        "5-second failover",
        "30-second drain",
        "zero remaining confirmed findings",
    ):
        assert required in combined


def test_wp6_non_claims_remain_explicit() -> None:
    combined = " ".join(" ".join(path.read_text(encoding="utf-8").split()) for path in (STATUS, DECISION, README, ROADMAP)).casefold()
    for required in (
        "no live etcd",
        "no live raft",
        "no live postgresql",
        "no live multi-host consensus",
        "no production ha",
        "no crash/reboot durability",
        "no cross-edge handover",
        "no cross-edge resumption",
        "no originset publication interoperability",
        "no new wire protocol",
        "no complete partition tolerance",
        "no global federation",
        "no production-readiness claim",
    ):
        assert required in combined


def test_wp6_does_not_overstate_file_repository_or_consensus_boundary() -> None:
    decision = " ".join(DECISION.read_text(encoding="utf-8").split()).casefold()
    assert "process-lifetime monotonic watermark" in decision
    assert "cooperating writers" in decision
    assert "stale lock" in decision
    assert "external compare-and-swap" in decision
