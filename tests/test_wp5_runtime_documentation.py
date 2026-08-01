from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STATUS = ROOT / "docs" / "protocol" / "status.md"
DECISION = ROOT / "docs" / "protocol" / "wp5-linux-gateway-packaging-decision.md"
README = ROOT / "README.md"
ROADMAP = ROOT / "docs" / "superpowers" / "plans" / "2026-07-28-v3.6-protocol-roadmap.md"


def test_wp5_completion_evidence_records_exact_fresh_counts() -> None:
    combined = STATUS.read_text(encoding="utf-8") + DECISION.read_text(encoding="utf-8")

    for required in (
        "903 passed and 1 skipped",
        "71 focused WP5 tests",
        "114 executable Rust tests and 16 doctests (130 total)",
        "125 files already formatted",
        "5/5",
        "8/8",
        "five candidates",
        "zero findings",
    ):
        assert required in combined


def test_wp5_public_status_is_complete_only_at_simulated_lab_scope() -> None:
    status = STATUS.read_text(encoding="utf-8")
    readme = README.read_text(encoding="utf-8")
    roadmap = ROADMAP.read_text(encoding="utf-8")

    assert "WP5 is complete at deterministic planning and simulated policy-conformance scope" in status
    assert "Deterministic Linux/OpenWrt gateway planning" in readme
    assert "WP5 deterministic Linux/OpenWrt gateway planning is complete" in roadmap
    assert "multi-service Service Channels" not in readme.split("## Explicit limitations", 1)[1]


def test_wp5_non_claims_remain_explicit() -> None:
    combined = "\n".join(path.read_text(encoding="utf-8") for path in (STATUS, DECISION, README, ROADMAP)).casefold()

    for required in (
        "no live nftables validation",
        "no live policy-routing validation",
        "no openwrt validation",
        "no clean no-agent client demonstration",
        "no operational rollback execution",
        "no privileged installer evidence",
        "no production-readiness claim",
    ):
        assert required in combined
