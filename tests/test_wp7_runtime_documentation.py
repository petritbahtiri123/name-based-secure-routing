from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STATUS = ROOT / "docs" / "protocol" / "status.md"
DECISION = ROOT / "docs" / "protocol" / "wp7-two-operator-isp-lab-decision.md"
README = ROOT / "README.md"
ROADMAP = ROOT / "docs" / "superpowers" / "plans" / "2026-07-28-v3.6-protocol-roadmap.md"


def _normalized(path: Path) -> str:
    if not path.exists():
        return ""
    return " ".join(path.read_text(encoding="utf-8").split())


def test_wp7_authoritative_docs_record_only_bounded_implemented_evidence() -> None:
    combined = " ".join(_normalized(path) for path in (STATUS, DECISION, README, ROADMAP))
    for required in (
        "WP7 is complete and evidence-closed at deterministic two-operator lab scope",
        "106 focused WP7 tests",
        "single-threaded, in-process",
        "source-first admission",
        "5-second source admission",
        "5-second destination admission",
        "30-second drain",
        "zero remaining confirmed findings",
    ):
        assert required in combined


def test_wp7_non_claims_remain_explicit() -> None:
    combined = " ".join(_normalized(path) for path in (STATUS, DECISION, README, ROADMAP)).casefold()
    for required in (
        "no production readiness",
        "no live two-isp deployment",
        "no independent real administration",
        "no real subscriber enforcement",
        "no ddos mitigation or elimination",
        "no origin anonymity",
        "no global federation",
        "no signed ownership or delegation",
        "no transparency",
        "no trust distribution or rotation",
        "no new wire protocol",
        "no originset publication interoperability",
        "no cross-edge handover or resumption",
        "no live consensus",
        "no complete partition tolerance",
        "no independent interoperability",
        "no raw-scan resistance outside the exact simulated topology",
    ):
        assert required in combined


def test_wp7_connector_and_runtime_boundaries_remain_explicit() -> None:
    decision = _normalized(DECISION).casefold()
    for required in (
        "origin endpoint remains confined to",
        "no network i/o",
        "exact registered capability object",
        "not derived from the origin endpoint",
        "one operatorpairruntime per modeled operator pair",
        "no process-global uniqueness",
        "no distributed replay protection",
        "no persistence",
        "no concurrency safety",
    ):
        assert required in decision
