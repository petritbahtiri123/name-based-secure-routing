from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STATUS = ROOT / "docs" / "protocol" / "status.md"
DECISION = ROOT / "docs" / "protocol" / "wp7-two-operator-isp-lab-decision.md"
README = ROOT / "README.md"
ROADMAP = ROOT / "docs" / "superpowers" / "plans" / "2026-07-28-v3.6-protocol-roadmap.md"


def _normalized(path: Path) -> str:
    return " ".join(path.read_text(encoding="utf-8").split())


def test_each_wp7_authoritative_doc_records_bounded_implemented_evidence() -> None:
    expectations = {
        STATUS: (
            "WP7 is complete and evidence-closed at deterministic two-operator lab scope",
            "106 focused WP7 tests",
            "1,077 passed and 1 skipped",
            "single-threaded, in-process",
        ),
        DECISION: (
            "WP7 is complete and evidence-closed at deterministic two-operator lab scope",
            "106 focused WP7 tests",
            "Source-first admission",
            "5-second source admission",
            "5-second destination admission",
            "30 seconds",
            "zero remaining confirmed findings",
        ),
        README: (
            "WP7 is complete and evidence-closed at deterministic two-operator lab scope",
            "106 focused WP7 tests",
            "1,077 passed and 1 skipped",
            "single-threaded, in-process",
        ),
        ROADMAP: (
            "WP7 is complete and evidence-closed at deterministic two-operator lab scope",
            "106 focused WP7 tests",
            "1,077 passed and 1 skipped",
            "single-threaded, in-process",
        ),
    }
    for path, required_statements in expectations.items():
        document = _normalized(path)
        for required in required_statements:
            assert required in document, f"{path.name} is missing: {required}"


def test_each_wp7_authoritative_doc_keeps_appropriate_non_claims() -> None:
    for path in (STATUS, DECISION, README, ROADMAP):
        document = _normalized(path).casefold()
        for required in (
            "no live two-isp deployment",
            "no origin anonymity",
            "no new wire protocol",
            "no independent interoperability",
        ):
            assert required in document, f"{path.name} is missing: {required}"


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
        "no production readiness",
        "no independent real administration",
        "no real subscriber enforcement",
        "no ddos mitigation or elimination",
        "no global federation",
        "no signed ownership or delegation",
        "no transparency",
        "no trust distribution or rotation",
        "no originset publication interoperability",
        "no cross-edge handover or resumption",
        "no live consensus",
        "no complete partition tolerance",
        "no raw-scan resistance outside the exact simulated topology",
    ):
        assert required in decision
