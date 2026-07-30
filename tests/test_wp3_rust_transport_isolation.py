from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
CRATE = ROOT / "crates" / "nbsr-transport"
DECISION = ROOT / "docs" / "protocol" / "wp3-single-service-transport-decision.md"
V36_DECISIONS = ROOT / "docs" / "protocol" / "v3.6-decisions.md"
ROADMAP = ROOT / "docs" / "superpowers" / "plans" / "2026-07-28-v3.6-protocol-roadmap.md"
STATUS = ROOT / "docs" / "protocol" / "status.md"


def _cargo_metadata() -> dict[str, object]:
    cargo = Path(os.environ["USERPROFILE"]) / ".cargo" / "bin" / "cargo.exe"
    result = subprocess.run(
        [
            str(cargo),
            "metadata",
            "--offline",
            "--locked",
            "--no-deps",
            "--format-version",
            "1",
            "--manifest-path",
            str(CRATE / "Cargo.toml"),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def test_rust_transport_dependencies_are_exact_and_locked() -> None:
    metadata = _cargo_metadata()
    package = metadata["packages"][0]
    actual = {dependency["name"]: dependency["req"] for dependency in package["dependencies"] if dependency["kind"] is None}

    assert actual == {
        "quinn": "=0.11.11",
        "rustls": "=0.23.43",
        "tokio": "=1.53.1",
        "x509-parser": "=0.18.1",
    }
    assert (CRATE / "Cargo.lock").is_file()


def test_python_runtime_does_not_import_invoke_or_embed_rust_transport() -> None:
    runtime_text = "\n".join(path.read_text(encoding="utf-8") for path in (ROOT / "nbsr").rglob("*.py")).casefold()

    for forbidden in ("nbsr-transport", "cargo.exe", "quinn_adapter", "ctypes.cdll"):
        assert forbidden not in runtime_text


def test_quinn_connection_operations_are_confined_to_adapter_source() -> None:
    offenders = []
    for path in (CRATE / "src").glob("*.rs"):
        if path.name == "quinn_adapter.rs":
            continue
        text = path.read_text(encoding="utf-8")
        if "Endpoint::" in text or "quinn::Connection" in text:
            offenders.append(path.name)

    assert offenders == []
    adapter = (CRATE / "src" / "quinn_adapter.rs").read_text(encoding="utf-8")
    assert "into_0rtt" not in adapter
    assert "open_bi" not in adapter
    assert "accept_bi" not in adapter


def test_no_certificate_or_private_key_fixture_is_committed() -> None:
    forbidden_suffixes = {".cer", ".crt", ".der", ".key", ".p12", ".pem", ".pfx"}
    committed_fixtures = [
        path.relative_to(CRATE).as_posix() for path in CRATE.rglob("*") if path.is_file() and path.suffix.casefold() in forbidden_suffixes
    ]

    assert committed_fixtures == []


def test_docs_record_observed_spike_without_authorizing_wp3_runtime() -> None:
    text = " ".join(
        (DECISION.read_text(encoding="utf-8") + V36_DECISIONS.read_text(encoding="utf-8") + ROADMAP.read_text(encoding="utf-8")).split()
    ).casefold()

    for required in (
        "quinn 0.11.11",
        "rustls 0.23.43",
        "11 handshake tests",
        "aioquic",
        "superseded",
        "handshake boundary",
        "no stream api",
        "wp3 runtime remains separately gated",
        "17 message codes remain unchanged",
        "19 error codes remain unchanged",
    ):
        assert required in text


def test_status_records_current_wp2_and_wp3_evidence_without_runtime_claims() -> None:
    text = " ".join(STATUS.read_text(encoding="utf-8").split()).casefold()

    for required in (
        "2026-07-30",
        "627 passed",
        "derived originset",
        "bounded legacy dns",
        "quinn 0.11.11",
        "11 handshake tests",
        "wp3 runtime remains gated",
    ):
        assert required in text
