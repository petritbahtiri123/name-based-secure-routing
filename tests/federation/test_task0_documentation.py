from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FILES = {
    name: ROOT / path
    for name, path in {
        "direction": "docs/protocol/wp8-federation-v0.1-direction.md",
        "design": "docs/superpowers/specs/2026-08-06-wp8-federation-v0.1-design.md",
        "plan": "docs/superpowers/plans/2026-08-06-wp8-federation-v0.1.md",
        "profile": "docs/protocol/federation-v0.1-development-profile.md",
        "decisions": "docs/protocol/wp8-federation-v0.1-decisions.md",
        "status": "docs/protocol/status.md",
        "roadmap": "docs/superpowers/plans/2026-07-28-v3.6-protocol-roadmap.md",
    }.items()
}


def _normalized(path: Path) -> str:
    return " ".join(path.read_text(encoding="utf-8").split())


def test_repository_contains_complete_decision_index_f1_f119_and_v1_v6() -> None:
    text = FILES["decisions"].read_text(encoding="utf-8")
    for prefix, end in (("F", 119), ("V", 6)):
        for number in range(1, end + 1):
            assert f"**{prefix}{number}.**" in text


def test_task0_documents_freeze_semantic_corrections() -> None:
    required = (
        "replay-state retention minimum: 86,400 seconds",
        "terminal tombstones are permanent",
        "continuity-preserving recovery",
        "lineage-breaking recovery",
        "registry and schema literal vectors",
        "python codecs and object validation",
        "stateful scenario manifests with literal expected outcomes",
        "no federation runtime is implemented by task 0",
    )
    for name in ("direction", "design", "plan", "profile"):
        text = _normalized(FILES[name]).casefold()
        for phrase in required:
            assert phrase in text, f"{name} missing {phrase}"


def test_profile_freeze_gate_names_every_preimplementation_decision() -> None:
    profile = _normalized(FILES["profile"]).casefold()
    for phrase in (
        "merkle leaf domain separator",
        "merkle node domain separator",
        "empty-tree root",
        "genesis checkpoint",
        "genesis/update requiredness",
        "privacy commitment",
        "opening rules",
        "signer-authority matrix",
        "cose kid",
        "root replacement",
        "operator id",
        "idempotency",
        "equivocation",
        "error precedence",
        "shared-transport",
        "independent-runtime",
    ):
        assert phrase in profile


def test_task0_status_is_proposal_not_implementation_or_wire_freeze() -> None:
    for name in FILES:
        text = _normalized(FILES[name]).casefold()
        if name in {"status", "roadmap", "direction", "design", "plan", "profile", "decisions"}:
            assert "task 0" in text
    profile = _normalized(FILES["profile"]).casefold()
    assert "proposed for human approval" in profile
    assert "not a permanently frozen federation wire allocation" in profile
    assert "no live federation" in profile


def test_terminal_and_recovery_errata_cover_every_required_surface() -> None:
    profile = _normalized(FILES["profile"]).casefold()
    for surface in (
        "garbage collection",
        "restart",
        "compaction",
        "backup restoration",
        "fresh-node synchronization",
    ):
        assert surface in profile
    assert "continuity-preserving recovery retains the operator id" in profile
    assert "lineage-breaking recovery terminally tombstones the old operator id" in profile


def test_authoritative_docs_remove_superseded_absolute_wording() -> None:
    for name in ("direction", "design"):
        text = _normalized(FILES[name]).casefold()
        assert "replay/tombstone retention minimum" not in text
        assert "recovery key rotation never changes" not in text
        assert "operational or recovery key rotation never changes" not in text
        assert "recovery never changes the stable genesis-derived operator id" not in text


def test_profile_names_requiredness_blocker_and_matches_signer_authority() -> None:
    profile = _normalized(FILES["profile"])
    assert "WP8-SCHEMA-REQUIREDNESS-01" in profile
    assert "blocks Tasks 2-6" in profile
    for exact in (
        "identity root / identity root",
        "operator endpoint or scoped delegate / endpoint discovery",
        "target controller 1-of-1, normal authority 3-of-5, or deny-only emergency authority 2-of-5 / revocation",
    ):
        assert exact in profile.casefold()
