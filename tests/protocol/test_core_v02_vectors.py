from __future__ import annotations

import os
import subprocess
import ipaddress
from hashlib import sha256
from pathlib import Path

import pytest

from nbsr.protocol.cbor import decode_deterministic, encode_deterministic
from nbsr.protocol.errors import ProtocolViolation
from nbsr.protocol.registry import MessageType
from scripts.core_v02_vectors.crypto import (
    verify_cose_sign1,
    verify_route_open,
)
from scripts.core_v02_vectors.fixtures import FIXTURES
from scripts.core_v02_vectors.generate import (
    build_package,
    build_invalid_artifacts,
    build_valid_package,
    run_scenario,
)
from scripts.core_v02_vectors.manifest import load_manifest, validate_package
from scripts.core_v02_vectors.reference import (
    ConformanceState,
    ReferenceContext,
    UnknownCoreVersion,
    apply_envelope,
    verify_envelope,
)
from scripts.generate_core_v02_vectors import check_package, write_package


ROOT = Path(__file__).resolve().parents[2]
COMMITTED = ROOT / "vectors" / "core-v0.2"


VALID_IDS = {
    "route-grant-payload",
    "route-grant-sign1",
    "client-hello-body",
    "client-hello",
    "edge-hello-body",
    "edge-hello",
    "route-open-proof-transcript",
    "route-open-proof-signature",
    "route-open",
    "route-accept",
    "route-reject",
    "stream-open",
    "stream-accept",
    "stream-reject",
}
INVALID_EXPECTATIONS = {
    "boolean-protocol-version": "NBSR_E_PROFILE_UNSUPPORTED",
    "cbor-duplicate-map-key": "NBSR_E_PROFILE_UNSUPPORTED",
    "cbor-float": "NBSR_E_PROFILE_UNSUPPORTED",
    "cbor-indefinite-map": "NBSR_E_PROFILE_UNSUPPORTED",
    "cbor-nonpreferred-integer": "NBSR_E_PROFILE_UNSUPPORTED",
    "cbor-over-total-bytes": "NBSR_E_OVER_CAPACITY",
    "cbor-trailing-bytes": "NBSR_E_PROFILE_UNSUPPORTED",
    "cbor-truncated": "NBSR_E_PROFILE_UNSUPPORTED",
    "cbor-unsupported-tag": "NBSR_E_PROFILE_UNSUPPORTED",
    "cbor-wrong-map-order": "NBSR_E_PROFILE_UNSUPPORTED",
    "cose-bad-signature": "NBSR_E_GRANT_INVALID",
    "cose-missing-tag": "NBSR_E_PROFILE_UNSUPPORTED",
    "cose-wrong-algorithm": "NBSR_E_PROFILE_UNSUPPORTED",
    "grant-expired": "NBSR_E_GRANT_EXPIRED",
    "proof-bad-signature": "NBSR_E_PROOF_INVALID",
    "route-port-not-authorized": "NBSR_E_ROUTE_DENIED",
    "version-one-on-v2": "NBSR_E_DOWNGRADE",
}


def _context() -> ReferenceContext:
    return ReferenceContext(
        expected_core_version=2,
        source_operator_id=FIXTURES.source_operator_id,
        source_edge_id=FIXTURES.source_edge_id,
        destination_operator_id=FIXTURES.destination_operator_id,
        destination_edge_id=FIXTURES.destination_edge_id,
        route_grant_issuer_public_key=FIXTURES.route_grant_public_key,
        route_grant_kid=FIXTURES.kid,
        client_session_public_key=FIXTURES.session_public_key,
        now=FIXTURES.opened_at,
        accepted_record_sequence=FIXTURES.record_sequence,
        max_clock_skew_seconds=60,
        expected_policy_hash=FIXTURES.policy_hash,
    )


def test_valid_package_contains_exact_approved_artifact_set() -> None:
    package = build_valid_package()

    assert {artifact.entry.id for artifact in package.artifacts} == VALID_IDS
    assert len(package.artifacts) == 14
    assert all(artifact.entry.vector_class == "valid" for artifact in package.artifacts)
    assert all(artifact.entry.expected_outcome == "accept" for artifact in package.artifacts)


def test_valid_cbor_artifacts_are_deterministic_and_hash_exact() -> None:
    package = build_valid_package()

    for artifact in package.artifacts:
        assert len(artifact.wire) == artifact.entry.length
        assert sha256(artifact.wire).hexdigest() == artifact.entry.sha256
        if artifact.entry.artifact_type in {
            "core-object-cbor",
            "control-envelope-cbor",
            "proof-transcript-cbor",
        }:
            assert artifact.wire == encode_deterministic(decode_deterministic(artifact.wire))


def test_valid_route_grant_cose_and_route_open_proof_verify() -> None:
    artifacts = build_valid_package().artifact_map()
    payload = verify_cose_sign1(
        artifacts["route-grant-sign1"],
        FIXTURES.route_grant_public_key,
        FIXTURES.kid,
    )
    assert payload == artifacts["route-grant-payload"]
    verify_route_open(
        artifacts["route-open-proof-transcript"],
        artifacts["route-open-proof-signature"],
        FIXTURES.session_public_key,
    )


def test_valid_envelopes_apply_through_stream_accept() -> None:
    artifacts = build_valid_package().artifact_map()
    state = ConformanceState()
    for vector_id in (
        "client-hello",
        "edge-hello",
        "route-open",
        "route-accept",
        "stream-open",
        "stream-accept",
    ):
        envelope = verify_envelope(artifacts[vector_id], _context())
        state = apply_envelope(state, envelope)

    assert state.transport_session_active
    assert FIXTURES.channel_id in state.active_channel_ids
    assert 4 in state.active_stream_ids


def test_route_and_stream_rejections_embed_safe_protocol_error() -> None:
    artifacts = build_valid_package().artifact_map()

    route_reject = verify_envelope(artifacts["route-reject"], _context())
    stream_reject = verify_envelope(artifacts["stream-reject"], _context())

    assert route_reject.message_type is MessageType.ROUTE_REJECT
    assert route_reject.protocol_error is not None
    assert stream_reject.message_type is MessageType.STREAM_REJECT
    assert stream_reject.protocol_error is not None


def test_invalid_vector_coverage_and_exact_error_mapping() -> None:
    valid = build_valid_package()
    invalid = build_invalid_artifacts(valid)

    assert {
        artifact.entry.id: artifact.entry.expected_error for artifact in invalid if artifact.entry.expected_outcome == "reject"
    } == INVALID_EXPECTATIONS
    close = [item for item in invalid if item.entry.expected_outcome == "close"]
    assert [item.entry.id for item in close] == ["version-three-generic-close"]
    assert close[0].entry.expected_error is None


def test_invalid_vectors_fail_at_the_declared_boundary() -> None:
    valid = build_valid_package()
    for artifact in build_invalid_artifacts(valid):
        if artifact.entry.expected_outcome == "close":
            try:
                verify_envelope(artifact.wire, _context())
            except UnknownCoreVersion:
                continue
            raise AssertionError(f"{artifact.entry.id} did not request generic close")
        try:
            if artifact.entry.artifact_type == "malformed-bytes":
                decode_deterministic(artifact.wire)
            else:
                verify_envelope(artifact.wire, _context())
        except ProtocolViolation as exc:
            assert exc.code.name == artifact.entry.expected_error, artifact.entry.id
            continue
        raise AssertionError(f"{artifact.entry.id} was unexpectedly accepted")


def test_scenario_registry_covers_only_approved_stateful_semantics() -> None:
    package = build_package()

    assert {scenario.id for scenario in package.manifest.scenarios} == {
        "accepted-route-stream-chain",
        "generic-close-no-fallback",
        "no-origin-disclosure",
        "no-route-before-admission",
        "no-stream-before-route-accept",
        "rejected-route-leaves-no-state",
        "request-replay-rejected",
        "version-mismatch-no-fallback",
    }


def test_all_scenarios_match_outcomes_and_preserve_rejected_state() -> None:
    package = build_package()
    artifacts = package.artifact_map()

    for scenario in package.manifest.scenarios:
        state = run_scenario(scenario, artifacts)
        if "transport-session-active" in scenario.final_assertions:
            assert state.transport_session_active
        if "route-context-active" in scenario.final_assertions:
            assert state.active_channel_ids
        if "stream-active" in scenario.final_assertions:
            assert state.active_stream_ids
        if "no-route-state" in scenario.final_assertions:
            assert not state.active_channel_ids
        if "no-stream-state" in scenario.final_assertions:
            assert not state.active_stream_ids


def test_write_and_check_package_are_byte_identical(tmp_path: Path) -> None:
    output = tmp_path / "core-v0.2"
    package = build_package()

    write_package(output, package)
    before = {path.relative_to(output).as_posix(): path.read_bytes() for path in output.rglob("*") if path.is_file()}
    check_package(output, package)
    after = {path.relative_to(output).as_posix(): path.read_bytes() for path in output.rglob("*") if path.is_file()}

    assert before == after
    assert "manifest.json" in before
    assert "README.md" in before


@pytest.mark.skipif(os.name != "nt", reason="Windows ACL regression")
def test_write_directory_inherits_parent_windows_acl(tmp_path: Path) -> None:
    output = tmp_path / "core-v0.2"

    write_package(output, build_package())
    result = subprocess.run(
        ["icacls", str(output)],
        check=True,
        capture_output=True,
        text=True,
    )

    assert "(I)" in result.stdout


@pytest.mark.parametrize("name", ["vectors", "other", "."])
def test_write_rejects_non_vector_target_names(tmp_path: Path, name: str) -> None:
    output = tmp_path / name

    with pytest.raises(ValueError, match="core-v0.2"):
        write_package(output, build_package())


def test_write_rejects_unrelated_nonempty_target(tmp_path: Path) -> None:
    output = tmp_path / "core-v0.2"
    output.mkdir()
    marker = output / "unrelated.txt"
    marker.write_text("preserve", encoding="utf-8")

    with pytest.raises(ValueError, match="owned package"):
        write_package(output, build_package())

    assert marker.read_text(encoding="utf-8") == "preserve"


def test_check_detects_missing_extra_and_changed_files(tmp_path: Path) -> None:
    package = build_package()
    for mutation in ("missing", "extra", "changed"):
        output = tmp_path / mutation / "core-v0.2"
        write_package(output, package)
        artifact = next((output / "artifacts").rglob("*.*"))
        if mutation == "missing":
            artifact.unlink()
        elif mutation == "extra":
            (output / "artifacts" / "extra.bin").write_bytes(b"x")
        else:
            artifact.write_bytes(artifact.read_bytes() + b"x")

        with pytest.raises(ValueError, match="package drift"):
            check_package(output, package)


def test_check_excludes_only_dedicated_wp4_exporter_subtree(tmp_path: Path) -> None:
    output = tmp_path / "core-v0.2"
    package = build_package()
    write_package(output, package)
    exporter_artifact = output / "wp4-exporter" / "valid" / "owned.bin"
    exporter_artifact.parent.mkdir(parents=True)
    exporter_artifact.write_bytes(b"owned by the WP4 exporter generator")

    check_package(output, package)

    unowned = output / "wp4-exporter-adjacent.bin"
    unowned.write_bytes(b"not owned by the WP4 exporter generator")
    with pytest.raises(ValueError, match="wp4-exporter-adjacent.bin"):
        check_package(output, package)


def _walk_text(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [text for item in value for text in _walk_text(item)]
    if isinstance(value, dict):
        return [text for key, item in value.items() for text in (*_walk_text(key), *_walk_text(item))]
    return []


def test_committed_package_validates_and_regenerates_byte_identically() -> None:
    manifest = load_manifest(COMMITTED / "manifest.json")

    validate_package(COMMITTED, manifest)
    check_package(COMMITTED, build_package())


def test_valid_artifacts_contain_no_ip_or_origin_text() -> None:
    manifest = load_manifest(COMMITTED / "manifest.json")
    texts: list[str] = []
    for entry in manifest.vectors:
        if entry.vector_class != "valid" or entry.artifact_type in {
            "ed25519-signature",
            "malformed-bytes",
        }:
            continue
        wire = (COMMITTED / entry.artifact_path).read_bytes()
        if entry.artifact_type == "cose-sign1":
            value = decode_deterministic(wire[1:])
        else:
            value = decode_deterministic(wire)
        texts.extend(_walk_text(value))

    assert all("origin" not in value.casefold() for value in texts)
    for value in texts:
        try:
            ipaddress.ip_address(value)
        except ValueError:
            continue
        raise AssertionError(f"valid vector exposes an IP literal: {value}")


def test_runtime_package_does_not_import_vector_tooling() -> None:
    for path in (ROOT / "nbsr").rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        assert "scripts.core_v02_vectors" not in source
        assert "generate_core_v02_vectors" not in source
