from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).parents[2]
PACKAGE = ROOT / "vectors/federation-v0.1"
GENERATOR = ROOT / "scripts/generate_federation_v01_vectors.py"
ARTIFACTS = {
    "README.md",
    "authority-locks.json",
    "capability-vectors.json",
    "error-precedence.json",
    "signed-vectors.json",
    "stateful-scenarios.json",
    "static-vectors.json",
    "threshold-vectors.json",
}


def load(name: str) -> dict[str, object]:
    return json.loads((PACKAGE / name).read_bytes())


def test_generator_builds_twice_identically_and_check_is_non_mutating(tmp_path: Path) -> None:
    first, second = tmp_path / "first", tmp_path / "second"
    for target in (first, second):
        subprocess.run([sys.executable, str(GENERATOR), str(target)], cwd=ROOT, check=True)
    first_files = {path.relative_to(first).as_posix(): path.read_bytes() for path in first.rglob("*") if path.is_file()}
    second_files = {path.relative_to(second).as_posix(): path.read_bytes() for path in second.rglob("*") if path.is_file()}
    assert first_files == second_files

    manifest = first / "manifest.json"
    original = manifest.read_bytes()
    manifest.write_bytes(original + b"\n")
    failed = subprocess.run([sys.executable, str(GENERATOR), "--check", str(first)], cwd=ROOT, capture_output=True, text=True)
    assert failed.returncode == 1
    assert manifest.read_bytes() == original + b"\n"


def test_checked_in_package_has_strict_closed_manifest() -> None:
    subprocess.run([sys.executable, str(GENERATOR), "--check", str(PACKAGE)], cwd=ROOT, check=True)
    manifest = load("manifest.json")
    assert set(manifest) == {"artifacts", "authority", "format_version", "package", "package_version"}
    assert manifest["format_version"] == 1
    assert manifest["package_version"] == "federation-v0.1-development-v1"
    entries = manifest["artifacts"]
    assert isinstance(entries, list)
    assert {entry["path"] for entry in entries} == ARTIFACTS
    assert len({entry["id"] for entry in entries}) == len(entries)
    assert len({entry["path"] for entry in entries}) == len(entries)
    expected_fields = {
        "class",
        "dependencies",
        "enforcement",
        "expected_outcome",
        "expected_reason",
        "expected_state_digest",
        "federation_version",
        "fixed_time",
        "id",
        "length",
        "mutation",
        "path",
        "profile",
        "sha256",
    }
    for entry in entries:
        assert set(entry) == expected_fields
        path = PACKAGE / entry["path"]
        assert path.is_file() and path.parent == PACKAGE
        assert entry["length"] == len(path.read_bytes())
        assert entry["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()


def test_static_and_signed_vectors_cover_registry_and_defect_families() -> None:
    static = load("static-vectors.json")
    signed = load("signed-vectors.json")
    registry = json.loads((ROOT / "docs/protocol/registries/federation-v0.1-development.json").read_bytes())
    objects = {item["name"] for item in registry["registries"]["object_types"]}
    assert len(objects) == 18
    assert {item["object_class"] for item in static["object_coverage"]} == objects
    assert {item["object_class"] for item in signed["object_coverage"]} == objects
    required = {
        "canonical-encoding",
        "requiredness",
        "wrong-type",
        "unknown-direct-field",
        "unknown-critical-extension",
        "malformed-cose",
        "invalid-signature",
        "wrong-kid",
        "wrong-key-purpose",
        "wrong-authority",
        "expired",
        "not-yet-valid",
        "wrong-operator",
        "wrong-scope",
        "rollback",
        "equivocation",
        "recovery",
        "revocation",
        "terminal-state",
        "resurrection",
        "resource-limits",
    }
    assert required <= {item["case"] for item in static["vectors"] + signed["vectors"]}
    for item in static["vectors"] + signed["vectors"]:
        assert {"dependencies", "expected", "fixed_context", "id", "mutation", "object_class"} <= set(item)
    assert all(bytes.fromhex(item["cose_sign1_hex"]).startswith(b"\xd2") for item in signed["vectors"] if item["expected"] == "ACCEPT")
    assert all(
        item["canonical_cbor_hex"] in {fixture["canonical_cbor_hex"] for fixture in static["schema_oracle"]}
        for item in static["vectors"]
        if item["provenance"] == "specification-authored"
    )


def test_signed_vectors_bind_the_same_payload_and_encode_wrong_kid_in_cose() -> None:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from nbsr.protocol.cose import verify_sign1
    from nbsr.protocol.errors import ProtocolViolation
    from nbsr.protocol.registry import ErrorCode

    package = load("signed-vectors.json")
    key = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(package["fixed_private_key_hex"])).public_key()
    for item in package["vectors"]:
        if item["case"] == "valid-sign1":
            verified = verify_sign1(
                bytes.fromhex(item["cose_sign1_hex"]), {bytes.fromhex(item["kid_hex"]): key}, ErrorCode.NBSR_E_RECORD_UNTRUSTED
            )
            assert hashlib.sha256(verified.payload).hexdigest() == item["payload_sha256"]
    wrong = next(item for item in package["vectors"] if item["case"] == "wrong-kid")
    with pytest.raises(ProtocolViolation):
        verify_sign1(
            bytes.fromhex(wrong["cose_sign1_hex"]), {bytes.fromhex(package["valid_kid_hex"]): key}, ErrorCode.NBSR_E_RECORD_UNTRUSTED
        )
    wrong_purpose = next(item for item in package["vectors"] if item["case"] == "wrong-key-purpose")
    assert wrong_purpose["authority_context"] == {"expected_key_purpose": 9, "registered_key_purpose": 1}


def test_threshold_vectors_reference_all_immutable_literals() -> None:
    packaged = load("threshold-vectors.json")
    oracle_path = ROOT / "vectors/federation-v0.1-threshold-container/literal-fixtures.json"
    oracle = json.loads(oracle_path.read_bytes())
    assert packaged["oracle_sha256"] == hashlib.sha256(oracle_path.read_bytes()).hexdigest()
    assert packaged["oracle_count"] == len(packaged["vectors"]) == len(oracle["fixtures"]) == 89
    assert [item["name"] for item in packaged["vectors"]] == [item["name"] for item in oracle["fixtures"]]
    for actual, expected in zip(packaged["vectors"], oracle["fixtures"], strict=True):
        assert actual["canonical_cbor_hex"] == expected["canonical_cbor_hex"]
        assert actual["sha256"] == expected["sha256"]


def test_schema_literals_and_upstream_authorities_are_independently_locked() -> None:
    static = load("static-vectors.json")
    schema_path = ROOT / "vectors/federation-v0.1-schema-proposal/literal-fixtures.json"
    schema = json.loads(schema_path.read_bytes())
    assert static["schema_oracle_count"] == len(schema["fixtures"]) == 28
    assert static["schema_oracle_sha256"] == hashlib.sha256(schema_path.read_bytes()).hexdigest()
    assert static["schema_oracle"] == schema["fixtures"]

    locks = load("authority-locks.json")
    assert locks["accepted_baseline_commit"] == "0849b986d065105441e116dce15294250a323926"
    assert locks["core_v02_artifact_count"] == 110
    assert locks["schema_literal_count"] == 28
    assert locks["task6_scenario_count"] == 4
    assert locks["threshold_literal_count"] == 89
    assert locks["threshold_evidence_capability"] == 6
    assert locks["federation_object_count"] == 18
    for item in locks["authorities"]:
        data = (ROOT / item["path"]).read_bytes()
        assert item["length"] == len(data)
        assert item["sha256"] == hashlib.sha256(data).hexdigest()


def test_capability_vectors_bind_capability_six_and_authenticated_session() -> None:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from nbsr.protocol.cbor import encode_deterministic
    from nbsr.protocol.cose import verify_sign1
    from nbsr.protocol.registry import ErrorCode

    package = load("capability-vectors.json")
    assert package["required_capability"] == {"id": 6, "name": "THRESHOLD_EVIDENCE"}
    required = {
        "valid-threshold-evidence",
        "threshold-evidence-absent",
        "capability-stripped",
        "duplicate-capability",
        "unknown-critical-capability",
        "unsupported-capability",
        "wrong-capability-set-digest",
        "wrong-authenticated-transcript-digest",
        "wrong-selected-core-version",
        "wrong-federation-version",
        "wrong-profile",
        "different-session-replay",
    }
    assert required == {item["case"] for item in package["vectors"]}
    valid = next(item for item in package["vectors"] if item["case"] == "valid-threshold-evidence")
    assert valid["agreed_capabilities"] == [6]
    assert valid["selected_core"] == "core-v0.2"
    assert valid["selected_federation"] == "federation-v0.1"
    assert valid["profile"] == "federation-v0.1-development"
    assert len(bytes.fromhex(valid["capability_set_digest"])) == 32
    assert len(bytes.fromhex(valid["authenticated_transcript_digest"])) == 32
    assert len(bytes.fromhex(valid["threshold_signature_context_digest"])) == 32
    assert bytes.fromhex(valid["offer_sign1_hex"]).startswith(b"\xd2")
    assert bytes.fromhex(valid["selection_sign1_hex"]).startswith(b"\xd2")
    assert len({item["threshold_signature_context_digest"] for item in package["vectors"]}) == len(package["vectors"])
    key = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(package["fixed_private_key_hex"])).public_key()
    for item in package["vectors"]:
        offer = verify_sign1(bytes.fromhex(item["offer_sign1_hex"]), {b"cap-offer": key}, ErrorCode.NBSR_E_RECORD_UNTRUSTED).payload
        selection = verify_sign1(
            bytes.fromhex(item["selection_sign1_hex"]), {b"cap-select": key}, ErrorCode.NBSR_E_RECORD_UNTRUSTED
        ).payload
        assert offer.hex() == item["offer_cbor_hex"]
        assert selection.hex() == item["selection_cbor_hex"]
        threshold = verify_sign1(
            bytes.fromhex(item["threshold_evidence_sign1_hex"]),
            {b"threshold-context": key},
            ErrorCode.NBSR_E_RECORD_UNTRUSTED,
        ).payload
        assert threshold.hex() == item["signed_threshold_signature_context_hex"]
        derived_capability = hashlib.sha256(encode_deterministic(item["agreed_capabilities"])).digest()
        derived_transcript = hashlib.sha256(offer + selection).digest()
        derived_context = hashlib.sha256(
            derived_capability + derived_transcript + bytes.fromhex(item["authenticated_session_digest"]) + b"threshold-evidence-v1"
        ).digest()
        if item["case"] not in {"wrong-capability-set-digest", "wrong-authenticated-transcript-digest", "different-session-replay"}:
            assert item["capability_set_digest"] == derived_capability.hex()
            assert item["authenticated_transcript_digest"] == derived_transcript.hex()
            assert threshold == derived_context
    replay = next(item for item in package["vectors"] if item["case"] == "different-session-replay")
    assert replay["replay_source_id"] == valid["id"]
    assert replay["threshold_evidence_sign1_hex"] == valid["threshold_evidence_sign1_hex"]
    assert replay["authenticated_session_digest"] != valid["authenticated_session_digest"]


def test_stateful_scenarios_cover_all_43_ordered_authorities_and_task6_oracle() -> None:
    package = load("stateful-scenarios.json")
    assert len(package["scenarios"]) == 43
    assert [item["ordinal"] for item in package["scenarios"]] == list(range(1, 44))
    required_fields = {
        "dependencies",
        "emitted_evidence",
        "enforcement",
        "evaluation_time",
        "expected_reason",
        "expected_result",
        "id",
        "input",
        "mutation",
        "ordinal",
        "resulting_state_digest",
        "effects",
    }
    assert all(set(item) == required_fields for item in package["scenarios"])
    assert all(len(bytes.fromhex(item["resulting_state_digest"])) == 32 for item in package["scenarios"])
    assert all({"artifact", "vector_id", "pre_state"} <= set(item["input"]) for item in package["scenarios"])
    assert all(item["effects"]["retained_state"] for item in package["scenarios"])
    event_ids = {item["id"] for item in package["event_vectors"]}
    assert {item["input"]["vector_id"] for item in package["scenarios"]} <= event_ids
    assert all(item["input"]["artifact"] == "stateful-scenarios.json" for item in package["scenarios"])
    task6_path = ROOT / "tests/federation/fixtures/task6-state-scenarios.json"
    assert package["task6_oracle_sha256"] == hashlib.sha256(task6_path.read_bytes()).hexdigest()
    assert package["task6_oracle"] == json.loads(task6_path.read_bytes())["scenarios"]


def test_all_stateful_scenarios_reexecute_through_federation_state() -> None:
    from nbsr.federation.registry import ReasonCode
    from nbsr.federation.state import FederationEvent, FederationState, StaticRecoveryPolicy

    package = load("stateful-scenarios.json")
    events = {item["id"]: item for item in package["event_vectors"]}
    policy = StaticRecoveryPolicy(
        b"P" * 32, (b"A" * 32, b"B" * 32), b"S" * 32, "static:route", ("control-outage",), 1_899_999_000, 1_900_001_000
    )
    state = FederationState.empty(static_policies=(policy,))
    for scenario in package["scenarios"]:
        vector = events[scenario["input"]["vector_id"]]
        raw = vector["federation_event"]
        event = FederationEvent(
            raw["key"],
            raw["generation"],
            raw["sequence"],
            bytes.fromhex(raw["object_digest"]),
            raw["object_kind"],
            bytes.fromhex(raw["operator_id"]),
            bytes.fromhex(raw["peer_operator_id"]),
            bytes.fromhex(raw["service_id"]),
            previous_digest=None if raw["previous_digest"] is None else bytes.fromhex(raw["previous_digest"]),
            dependencies=tuple(bytes.fromhex(value) for value in raw["dependencies"]),
            valid_until=raw["valid_until"],
            source_fresh_at=raw["source_fresh_at"],
            terminal=raw["terminal"],
            compromised=raw["compromised"],
            replay_digest=None if raw["replay_digest"] is None else bytes.fromhex(raw["replay_digest"]),
            validation_failures=tuple(ReasonCode[value] for value in raw["validation_failures"]),
            operation=raw["operation"],
            requires_prior_authority=raw["requires_prior_authority"],
            recovery_of=raw["recovery_of"],
            static_policy_digest=None if raw["static_policy_digest"] is None else bytes.fromhex(raw["static_policy_digest"]),
            outage_trigger=raw["outage_trigger"],
            authority_expansion=raw["authority_expansion"],
        )
        assert state.digest.hex() == scenario["input"]["pre_state"]
        state, result = state.apply(event, vector["evaluation_time"])
        assert (result.outcome.name, result.reason.name, result.enforcement.name, result.state_changed) == (
            scenario["expected_result"],
            scenario["expected_reason"],
            scenario["enforcement"],
            scenario["mutation"],
        )
        assert state.digest.hex() == scenario["resulting_state_digest"]


def test_error_precedence_has_all_ranks_and_simultaneous_defects() -> None:
    package = load("error-precedence.json")
    assert [item["rank"] for item in package["precedence"]] == list(range(1, 12))
    assert all(len(item["defects"]) >= 2 for item in package["vectors"])
    rank = {item["reason"]: item["rank"] for item in package["precedence"]}
    for item in package["vectors"]:
        assert item["expected_reason"] == min(item["defects"], key=rank.__getitem__)


@pytest.mark.parametrize("unsafe", ["../escape.json", "/absolute.json", "a\\b.json", "", ".", "manifest.json"])
def test_manifest_rejects_unsafe_or_recursive_paths(tmp_path: Path, unsafe: str) -> None:
    from scripts.federation_v01_vectors.package import validate_manifest

    manifest = {"format_version": 1, "package_version": "federation-v0.1-development-v1", "artifacts": [{"id": "x", "path": unsafe}]}
    with pytest.raises(ValueError):
        validate_manifest(manifest, tmp_path)


def test_manifest_rejects_unknown_fields_corrupt_metadata_and_dependency_cycles(tmp_path: Path) -> None:
    from scripts.federation_v01_vectors.package import build_package, validate_manifest, write_package

    write_package(tmp_path)
    manifest = json.loads(build_package()["manifest.json"])
    manifest["unknown"] = True
    with pytest.raises(ValueError):
        validate_manifest(manifest, tmp_path)
    manifest.pop("unknown")
    manifest["artifacts"][0]["sha256"] = "00" * 32
    with pytest.raises(ValueError):
        validate_manifest(manifest, tmp_path)
    manifest = json.loads(build_package()["manifest.json"])
    manifest["artifacts"][0]["dependencies"] = [manifest["artifacts"][1]["id"]]
    manifest["artifacts"][1]["dependencies"] = [manifest["artifacts"][0]["id"]]
    with pytest.raises(ValueError):
        validate_manifest(manifest, tmp_path)
    nested = tmp_path / "extra"
    nested.mkdir()
    (nested / "unlisted.json").write_text("{}", encoding="ascii")
    manifest = json.loads(build_package()["manifest.json"])
    with pytest.raises(ValueError):
        validate_manifest(manifest, tmp_path)


def test_generator_refuses_expected_file_symlink(tmp_path: Path) -> None:
    from scripts.federation_v01_vectors.package import write_package

    package = tmp_path / "package"
    package.mkdir()
    outside = tmp_path / "outside"
    outside.write_bytes(b"do-not-touch")
    try:
        (package / "README.md").symlink_to(outside)
    except OSError:
        pytest.skip("symlink creation unavailable")
    with pytest.raises(ValueError):
        write_package(package)
    assert outside.read_bytes() == b"do-not-touch"
