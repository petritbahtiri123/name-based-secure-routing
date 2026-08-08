from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
from nbsr.protocol.cbor import decode_deterministic, encode_deterministic
from nbsr.protocol.cose import sign1


ROOT = Path(__file__).resolve().parents[2]
PEER = ROOT / "interop" / "nbsr-go-peer"
TRANSPORT = ROOT / "crates" / "nbsr-transport"


def _write_test_authority(directory: Path) -> None:
    directory.mkdir()
    now = __import__("datetime").datetime.now(__import__("datetime").UTC)
    ca_key = ec.generate_private_key(ec.SECP256R1())
    ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Task 10B Test CA")])
    ca = (
        x509.CertificateBuilder()
        .subject_name(ca_name)
        .issuer_name(ca_name)
        .public_key(ca_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - __import__("datetime").timedelta(minutes=1))
        .not_valid_after(now + __import__("datetime").timedelta(days=1))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(ca_key, hashes.SHA256())
    )
    (directory / "ca.der").write_bytes(ca.public_bytes(serialization.Encoding.DER))
    for stem, name in (("source", "source.edge"), ("destination", "destination.edge")):
        key = ec.generate_private_key(ec.SECP256R1())
        subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, name)])
        cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(ca.subject)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - __import__("datetime").timedelta(minutes=1))
            .not_valid_after(now + __import__("datetime").timedelta(days=1))
            .add_extension(x509.SubjectAlternativeName([x509.DNSName(name)]), critical=False)
            .add_extension(
                x509.ExtendedKeyUsage(
                    [ExtendedKeyUsageOID.CLIENT_AUTH, ExtendedKeyUsageOID.SERVER_AUTH]
                ),
                critical=False,
            )
            .sign(ca_key, hashes.SHA256())
        )
        (directory / f"{stem}.der").write_bytes(cert.public_bytes(serialization.Encoding.DER))
        (directory / f"{stem}-key.der").write_bytes(
            key.private_bytes(
                serialization.Encoding.DER,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            )
        )


def _build_go_peer(output: Path) -> Path:
    configured = os.environ.get("NBSR_TASK10B_GO_PEER")
    if configured:
        return Path(configured)
    executable = output / ("nbsr-go-peer.exe" if sys.platform == "win32" else "nbsr-go-peer")
    build = subprocess.run(
        ["go", "build", "-trimpath", "-o", str(executable), "./cmd/nbsr-go-peer"],
        cwd=PEER, capture_output=True, text=True, timeout=120, check=False,
    )
    assert build.returncode == 0, build.stderr
    return executable


def _expired_source_attestation(case: Path) -> Path:
    package = case / "expired-local-admission"
    package.mkdir()
    wire = (ROOT / "vectors/wp8-local-admission/source.cose").read_bytes()
    assert wire[0] == 0xD2
    cose = decode_deterministic(wire[1:])
    payload = decode_deterministic(cose[2])
    payload[11] = 1_893_455_999
    (package / "source.cose").write_bytes(sign1(
        encode_deterministic(payload), b"local-source",
        Ed25519PrivateKey.from_private_bytes(b"S" * 32),
    ))
    return package
def test_cross_process_go_source_exchanges_frozen_route_and_stream(tmp_path: Path) -> None:
    target = Path(os.environ.get("NBSR_TASK10B_CARGO_TARGET", tmp_path / "cargo-target"))
    build = subprocess.run(
        [
            "cargo",
            "build",
            "--manifest-path",
            str(TRANSPORT / "Cargo.toml"),
            "--bin",
            "wp8_interop_server",
        ],
        cwd=ROOT,
        env={**os.environ, "CARGO_TARGET_DIR": str(target)},
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    assert build.returncode == 0, build.stderr
    peer_executable = _build_go_peer(tmp_path)

    server_exe = target / "debug" / (
        "wp8_interop_server.exe" if sys.platform == "win32" else "wp8_interop_server"
    )
    ready = tmp_path / "ready.json"
    result = tmp_path / "server-result.json"
    completion_ack = tmp_path / "peer-complete.ack"
    authority_dir = tmp_path / "authority"
    _write_test_authority(authority_dir)
    server = subprocess.Popen(
        [
            str(server_exe),
            "--ready",
            str(ready),
            "--result",
            str(result),
            "--authority-dir",
            str(authority_dir),
            "--completion-ack",
            str(completion_ack),
        ],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        deadline = time.monotonic() + 10
        while not ready.exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        assert ready.exists(), server.stderr.read()
        readiness = json.loads(ready.read_text(encoding="utf-8"))
        assert set(readiness) == {
            "alpn",
            "ca_der",
            "client_cert_der",
            "client_key_der",
            "endpoint",
            "quic_version",
            "server_name",
            "tls_version",
        }
        assert readiness["alpn"] == "nbsr-quic-1"
        config = tmp_path / "peer-config.json"
        config.write_text(
            json.dumps(
                {
                    "readiness_path": str(ready),
                    "f75_package": str(ROOT / "vectors" / "wp8-f75-route-open"),
                    "local_attestation_package": str(
                        ROOT / "vectors" / "wp8-local-admission"
                    ),
                    "safe_payload": "NBSR-WP8-TASK10B-INDEPENDENT-WIRE",
                },
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        peer = subprocess.run(
            [str(peer_executable), "--config", str(config)],
            cwd=PEER,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        completion_ack.touch()
        time.sleep(0.05)
        server_error = server.stderr.read() if server.poll() is not None else "server still running"
        assert peer.returncode == 0, f"peer: {peer.stderr}\nserver: {server_error}"
        observed = json.loads(peer.stdout)
        assert observed["status"] == "PASS"
        assert observed["messages"] == [
            "CLIENT_HELLO",
            "EDGE_HELLO",
            "ROUTE_OPEN",
            "ROUTE_ACCEPT",
            "STREAM_OPEN",
            "STREAM_ACCEPT",
        ]
        assert observed["core_version"] == 2
        assert observed["route_open_body_version"] == 2
        assert observed["federation_profile"] == "nbsr-federation-dev-v1"
        assert observed["payload_sha256"] == (
            "049aa2fdcaa4fa7cbaa5cf20d35d831ecf47722633be6e2bcf02a16233d93112"
        )
        deadline = time.monotonic() + 5
        while server.poll() is None and time.monotonic() < deadline:
            time.sleep(0.01)
        assert server.returncode == 0, server.stderr.read()
        assert json.loads(result.read_text(encoding="utf-8")) == {
            "payload_bytes": 33,
            "payload_sha256": "049aa2fdcaa4fa7cbaa5cf20d35d831ecf47722633be6e2bcf02a16233d93112",
            "status": "PASS",
        }
    finally:
        if server.poll() is None:
            server.terminate()
        server.communicate(timeout=10)


def test_go_peer_is_implementation_independent() -> None:
    sources = sorted(PEER.rglob("*.go"))
    assert sources, "independent Go peer source is absent"
    combined = "\n".join(path.read_text(encoding="utf-8") for path in sources)
    forbidden = (
        r"verifiers[/\\]federation-go",
        r"crates[/\\]nbsr-transport",
        r'os/exec',
        r'import\s+"C"',
        r'unsafe',
        r'expected_(?:result|message|transcript|exporter|accept)',
    )
    for pattern in forbidden:
        assert re.search(pattern, combined, flags=re.IGNORECASE) is None, pattern


def test_go_peer_cli_rejects_unknown_configuration_authority(tmp_path: Path) -> None:
    config = tmp_path / "config.json"
    config.write_text(
        json.dumps(
            {
                "readiness_path": str(tmp_path / "ready.json"),
                "f75_package": str(ROOT / "vectors" / "wp8-f75-route-open"),
                "local_attestation_package": str(
                    ROOT / "vectors" / "wp8-local-admission"
                ),
                "safe_payload": "NBSR-WP8-TASK10B-INDEPENDENT-WIRE",
                "expected_result": "PASS",
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    executable = tmp_path / ("nbsr-go-peer.exe" if sys.platform == "win32" else "nbsr-go-peer")
    build = subprocess.run(
        ["go", "build", "-trimpath", "-o", str(executable), "./cmd/nbsr-go-peer"],
        cwd=PEER,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert build.returncode == 0, build.stderr
    process = subprocess.run(
        [str(executable), "--config", str(config)],
        cwd=PEER,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert process.returncode != 0
    assert "unknown field" in process.stderr
    assert process.stdout == ""


def test_live_negative_interoperability_matrix_fails_before_payload(tmp_path: Path) -> None:
    target = tmp_path / "cargo-target"
    build = subprocess.run(
        ["cargo", "build", "--manifest-path", str(TRANSPORT / "Cargo.toml"), "--bin", "wp8_interop_server"],
        cwd=ROOT,
        env={**os.environ, "CARGO_TARGET_DIR": str(target)},
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    assert build.returncode == 0, build.stderr
    peer_executable = _build_go_peer(tmp_path)
    server_exe = target / "debug" / ("wp8_interop_server.exe" if sys.platform == "win32" else "wp8_interop_server")
    mutations = (
        "unsupported_alpn", "wrong_peer_identity", "wrong_ca",
        "payload_before_admission", "malformed_cbor", "noncanonical_cbor", "over_limit_cbor", "wrong_core_version",
        "wrong_session", "wrong_request", "wrong_channel", "wrong_transport",
        "wrong_port", "wrong_route_grant_digest", "wrong_federation_context_digest",
        "wrong_proof_signature", "wrong_service", "expired_authority", "revoked_authority", "unsupported_federation_version",
        "unsupported_profile", "downgrade_v1", "transcript_substitution", "replay",
        "wrong_stream",
    )
    destination_rejections = set(mutations) - {
        "unsupported_alpn", "wrong_peer_identity", "wrong_ca",
        "payload_before_admission", "wrong_port", "expired_authority",
    }
    evidence = json.loads((ROOT / "evidence/wp8-task10b/independent-wire-result.json").read_text(encoding="utf-8"))
    assert set(evidence["negative_observations"]) == set(mutations)
    assert all(observation[2] == 0 for observation in evidence["negative_observations"].values())
    for mutation in mutations:
        case = tmp_path / mutation
        case.mkdir()
        ready, result, ack = case / "ready.json", case / "server-result.json", case / "complete.ack"
        authority_dir = case / "authority"
        _write_test_authority(authority_dir)
        server = subprocess.Popen(
            [str(server_exe), "--ready", str(ready), "--result", str(result), "--authority-dir", str(authority_dir), "--completion-ack", str(ack)],
            cwd=ROOT,
            env={**os.environ, **({"NBSR_TASK10B_REVOKE_DESTINATION_AUTHORITY": "1"} if mutation == "revoked_authority" else {})},
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            deadline = time.monotonic() + 10
            while not ready.exists() and time.monotonic() < deadline:
                time.sleep(0.01)
            assert ready.exists(), f"{mutation}: server did not become ready"
            config = case / "peer-config.json"
            local_package = _expired_source_attestation(case) if mutation == "expired_authority" else ROOT / "vectors" / "wp8-local-admission"
            config.write_text(json.dumps({
                "readiness_path": str(ready),
                "f75_package": str(ROOT / "vectors" / "wp8-f75-route-open"),
                "local_attestation_package": str(local_package),
                "safe_payload": "NBSR-WP8-TASK10B-INDEPENDENT-WIRE",
            }, sort_keys=True), encoding="utf-8")
            peer = subprocess.run(
                [str(peer_executable), "--config", str(config)],
                cwd=PEER,
                env={**os.environ, "NBSR_INTEROP_TEST_MUTATION": mutation},
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
            assert peer.returncode != 0, f"{mutation}: mutation unexpectedly succeeded: {peer.stdout}"
            assert not result.exists(), f"{mutation}: destination accepted application payload"
            if mutation == "expired_authority":
                assert "source federation admission" in peer.stderr
            elif mutation == "wrong_port":
                assert "route authority binding mismatch" in peer.stderr
            elif mutation == "payload_before_admission":
                assert "test payload attempted before admission" in peer.stderr
            elif mutation in destination_rejections:
                deadline = time.monotonic() + 3
                while server.poll() is None and time.monotonic() < deadline:
                    time.sleep(0.01)
                assert server.returncode not in (None, 0), f"{mutation}: destination rejection was not observed"
        finally:
            ack.touch()
            if server.poll() is None:
                server.terminate()
            server.communicate(timeout=10)
