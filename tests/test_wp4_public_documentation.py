from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_project_history_records_wp4_without_expanding_its_lab_scope() -> None:
    history = read("docs/project-history.md")
    required = (
        "WP4 — reusable multi-service transport slice",
        "32 isolated Service Channels",
        "64 reliable streams per channel",
        "fresh RouteGrant and nonce",
        "TLS exporter",
        "canonical channel context",
        "Python, Node.js, and Rust",
        "same-edge resume",
        "does not select an OriginSet",
        "connect to or forward traffic to an Origin Endpoint",
        "integrate NameRelay",
        "cross-edge resume",
        "0-RTT",
    )
    for text in required:
        assert text in history


def test_security_policy_includes_wp4_authority_and_containment_surfaces() -> None:
    security = read("SECURITY.md")
    required = (
        "Service Channel isolation",
        "TLS exporter or channel binding",
        "per-service authorization",
        "quota or audit containment",
        "drain or same-edge resume authority",
    )
    for text in required:
        assert text in security


def test_contributor_checks_cover_locked_rust_and_owned_vector_packages() -> None:
    contributing = read("CONTRIBUTING.md")
    required = (
        "cargo test --locked --manifest-path crates/nbsr-transport/Cargo.toml",
        "cargo clippy --locked --manifest-path crates/nbsr-transport/Cargo.toml",
        "python scripts/generate_core_v02_vectors.py --check",
        "python scripts/generate_wp4_exporter_vectors.py --check",
        "node scripts/verify_wp4_exporter_vectors.mjs vectors/core-v0.2/wp4-exporter",
    )
    for text in required:
        assert text in contributing
