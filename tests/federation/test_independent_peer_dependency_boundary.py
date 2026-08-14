from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[2]
PEER = ROOT / "interop" / "nbsr-go-peer"


def test_independent_peer_dependency_is_exact_isolated_and_checksum_locked() -> None:
    module = (PEER / "go.mod").read_text(encoding="utf-8")
    assert re.search(r"(?m)^go 1\.26\.5$", module)
    assert re.search(r"(?m)^require github\.com/quic-go/quic-go v0\.61\.0$", module)
    assert "replace " not in module
    assert "verifiers/federation-go" not in module
    assert "nbsr-transport" not in module

    sums = (PEER / "go.sum").read_text(encoding="utf-8")
    assert ("github.com/quic-go/quic-go v0.61.0 h1:ui88A53s8MSVYLC56en0KQ17HARk+9986Dn0SBfKNvA=") in sums
    lock = json.loads((PEER / "dependency-lock.json").read_text(encoding="utf-8"))
    assert [entry["path"] for entry in lock["files"]] == ["interop/nbsr-go-peer/go.mod", "interop/nbsr-go-peer/go.sum"]
    for entry in lock["files"]:
        wire = (ROOT / entry["path"]).read_bytes()
        assert entry["length"] == len(wire)
        assert entry["sha256"] == hashlib.sha256(wire).hexdigest()


def test_dependency_evidence_records_executed_cross_stack_proofs() -> None:
    evidence = (PEER / "DEPENDENCIES.md").read_text(encoding="utf-8")
    for required in (
        "quic-go v0.61.0",
        "MIT",
        "Go 1.26.5",
        "nbsr-quic-1",
        "mutual TLS: PASS",
        "bidirectional stream IDs: PASS",
        "0-RTT disabled: PASS",
        "public TLS exporter: PASS",
        "Go/Rust exporter parity: PASS",
        "aioquic 1.3.0: REJECTED",
        "govulncheck: PASS",
        "Disposable proof command:",
    ):
        assert required in evidence
    proof = PEER / "feasibility-result.json"
    assert proof.exists()
    assert hashlib.sha256(proof.read_bytes()).hexdigest() in evidence

    result = json.loads(proof.read_text(encoding="utf-8"))
    assert result["go"]["quic_version"] == "v1"
    assert result["go"]["tls_version"] == 772
    assert result["go"]["alpn"] == "nbsr-quic-1"
    assert result["go"]["used_0rtt"] is False
    assert result["go"]["key_log_disabled"] is True
    assert result["go"]["exporter_length"] == 32
    assert result["go"]["exporter_sha256"] == result["rust"]["exporter_sha256"]
    assert result["negative"]["unsupported_alpn"] == "REJECTED"
    assert result["negative"]["wrong_identity"] == "REJECTED"
    assert result["negative"]["wrong_ca"] == "REJECTED"
    assert result["negative"]["missing_client_certificate"] == "REJECTED"


def test_task10b_runner_is_wired_into_wp8_without_independent_peer_skip() -> None:
    task10b = (ROOT / "scripts" / "verify_wp8_task10b.py").read_text(encoding="utf-8")
    for required in ("go-peer-unit", "go-peer-vet", "go-peer-module-lock", "independent-wire-live", "git-diff-check"):
        assert required in task10b
    wp8 = (ROOT / "scripts" / "verify_wp8_conformance.py").read_text(encoding="utf-8")
    assert 'Command("independent-wire-peer", (python, "scripts/verify_wp8_task10b.py"))' in wp8
    assert "independent route/stream wire interoperability NOT YET PROVEN" not in wp8
    assert wp8.count("--ignore=tests/federation/test_independent_wire_peer.py") == 2
