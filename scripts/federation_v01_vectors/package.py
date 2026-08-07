from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path, PurePosixPath

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from nbsr.protocol.cbor import decode_deterministic, encode_deterministic
from nbsr.protocol.cose import sign1
from nbsr.federation.profile import FederationProfile
from nbsr.federation.registry import ReasonCode
from nbsr.federation.state import FederationEvent, FederationState, StaticRecoveryPolicy


ROOT = Path(__file__).parents[2]
FIXED_TIME = 1_900_000_000
PACKAGE_VERSION = "federation-v0.1-development-v1"
PROFILE = "federation-v0.1-development"
KEY = Ed25519PrivateKey.from_private_bytes(bytes.fromhex("1f" * 32))
KID = bytes.fromhex("a1b2c3d4e5f60708")
OBJECTS = (
    "OperatorRegistryRecord",
    "KeyAuthorizationRecord",
    "NameOwnershipRecord",
    "DelegationRecord",
    "FederationTrustBundle",
    "TransparencyCheckpoint",
    "InclusionProof",
    "ConsistencyProof",
    "WitnessStatement",
    "OperatorEndpointRecord",
    "FederationAuthorityProof",
    "FederationAuthorizationContext",
    "TypedRevocationRecord",
    "ConflictEvidence",
    "OperatorLifecycleRecord",
    "RecoveryTransitionRecord",
    "ConflictResolutionRecord",
    "AppealDecisionRecord",
)
AUTHORITY_LOCKS = (
    ("docs/protocol/core-v0.1-wire.md", 20532, "297a24699381958674c4d30826912c835d80fb8d336807eb972b9574297291a3"),
    ("docs/protocol/registries/core-v0.2-baseline-lock.json", 21103, "21d60dc60ee1bc00bef882b63fabaaea9229768770912ed7c93e6ae4d54453ef"),
    (
        "docs/protocol/registries/federation-v0.1-development.json",
        78624,
        "29311cb8e952e328eef7c69fb4776a85504ff4af5edf7c55faad53194d60dc7e",
    ),
    (
        "docs/protocol/registries/federation-v0.1-schema-proposal.json",
        213045,
        "de0a3e6bf7b679408974137bcbb3b642137ae1584856b21db2c0bd4852166410",
    ),
    (
        "vectors/federation-v0.1-schema-proposal/literal-fixtures.json",
        35228,
        "47af31ea9d1bad21f425e2174e9fefaf36116ca0134b75365a2770185f0d80c8",
    ),
    ("tests/federation/fixtures/task6-state-scenarios.json", 2779, "6829213bac524a2c98e7b24f73ccc18d21a3068d5881ebef0973eb3fe86ac342"),
    (
        "docs/protocol/registries/federation-v0.1-threshold-container-proposal.json",
        9772,
        "d09e78c21a149e91a73f0da32b723a0038937da12c6543cbf1a7605c7e7acf08",
    ),
    (
        "vectors/federation-v0.1-threshold-container/literal-fixtures.json",
        568088,
        "5cd780332fae841bfab6a31cc362b00d28071264b11b43b55f1a40bfc6228e9a",
    ),
)


def _json(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")) + "\n").encode("ascii")


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _fixed_context() -> dict[str, object]:
    return {
        "capabilities": [6],
        "core": "core-v0.2",
        "evaluation_time": FIXED_TIME,
        "federation": "federation-v0.1",
        "profile": PROFILE,
        "session_transcript_digest": _sha(b"nbsr-federation-v0.1-session-a"),
    }


def _static_vectors() -> dict[str, object]:
    oracle_path = ROOT / "vectors/federation-v0.1-schema-proposal/literal-fixtures.json"
    raw = oracle_path.read_bytes()
    oracle = json.loads(raw)

    def category(name: str) -> str:
        for needle, value in (
            ("missing", "requiredness"),
            ("unknown-critical", "unknown-critical-extension"),
            ("wrong-key-purpose", "wrong-key-purpose"),
            ("bad-kid", "wrong-kid"),
            ("expired", "expired"),
            ("stale", "rollback"),
            ("conflicting", "equivocation"),
            ("recovery", "recovery"),
            ("terminal", "terminal-state"),
            ("invalid-signer", "wrong-authority"),
            ("mismatch", "wrong-scope"),
        ):
            if needle in name:
                return value
        return "canonical-encoding" if name.startswith("valid-") else "schema-validation"

    vectors = [
        {
            "canonical_cbor_hex": item["canonical_cbor_hex"],
            "case": category(item["name"]),
            "dependencies": [],
            "expected": item["expected_outcome"],
            "expected_reason": item["reason"],
            "fixed_context": item["validation_context"],
            "id": f"schema-oracle-{item['name']}",
            "mutation": item["state_changed"],
            "object_class": item["object_type"],
            "payload_sha256": item["sha256"],
            "provenance": "specification-authored",
            "resource_expectation": "oracle-defined",
        }
        for item in oracle["fixtures"]
    ]
    genesis = next(item for item in oracle["fixtures"] if item["name"] == "valid-genesis")
    base = decode_deterministic(bytes.fromhex(genesis["canonical_cbor_hex"]))
    mutations = []
    for case, mutate, reason in (
        ("wrong-type", lambda value: {**value, 4: True}, "ERR_SCHEMA"),
        ("unknown-direct-field", lambda value: {**value, 126: b"unknown"}, "ERR_SCHEMA"),
    ):
        payload = encode_deterministic(mutate(base))
        mutations.append(
            {
                "canonical_cbor_hex": payload.hex(),
                "case": case,
                "dependencies": ["schema-oracle-valid-genesis"],
                "expected": "REJECT",
                "expected_reason": reason,
                "fixed_context": genesis["validation_context"],
                "id": f"static-negative-{case}",
                "mutation": False,
                "mutation_of": "schema-oracle-valid-genesis",
                "object_class": "OperatorRegistryRecord",
                "payload_sha256": _sha(payload),
                "provenance": "reference-generated-mutation",
                "resource_expectation": "reject-before-mutation",
            }
        )
    for case, source_name, reason, context_change in (
        ("not-yet-valid", "valid-genesis", "ERR_FRESHNESS", {"validation_time": 99}),
        ("wrong-operator", "valid-genesis", "ERR_IDENTITY", {"expected_operator_id": "ff" * 32}),
        ("revocation", "compromised-signer", "ERR_KEY_LIFECYCLE", {}),
        ("resurrection", "terminal-key-id-reuse", "ERR_TERMINAL_STATE", {}),
    ):
        source = next(item for item in oracle["fixtures"] if item["name"] == source_name)
        context = {**source["validation_context"], **context_change}
        mutations.append(
            {
                "canonical_cbor_hex": source["canonical_cbor_hex"],
                "case": case,
                "dependencies": [f"schema-oracle-{source_name}"],
                "expected": "REJECT",
                "expected_reason": reason,
                "fixed_context": context,
                "id": f"static-negative-{case}",
                "mutation": False,
                "mutation_of": f"schema-oracle-{source_name}",
                "object_class": source["object_type"],
                "payload_sha256": source["sha256"],
                "provenance": "reference-generated-context-mutation",
                "resource_expectation": "reject-before-mutation",
            }
        )
    oversized = b"x" * 32_769
    mutations.append(
        {
            "canonical_cbor_hex": oversized.hex(),
            "case": "resource-limits",
            "dependencies": [],
            "expected": "REJECT",
            "expected_reason": "ERR_RESOURCE_LIMIT",
            "fixed_context": genesis["validation_context"],
            "id": "static-negative-resource-limits",
            "mutation": False,
            "mutation_of": None,
            "object_class": "OperatorRegistryRecord",
            "payload_sha256": _sha(oversized),
            "provenance": "reference-generated-mutation",
            "resource_expectation": "reject-before-decode",
        }
    )
    vectors.extend(mutations)
    coverage = [
        {
            "object_class": name,
            "vector_ids": [item["id"] for item in vectors if item["object_class"] == name],
            "coverage_source": "schema-literal"
            if any(item["object_class"] == name for item in vectors)
            else "threshold-or-stateful-scenario",
        }
        for name in OBJECTS
    ]
    return {
        "authority": "Federation v0.1 static conformance vectors",
        "format_version": 1,
        "object_coverage": coverage,
        "schema_oracle": oracle["fixtures"],
        "schema_oracle_count": len(oracle["fixtures"]),
        "schema_oracle_path": "../federation-v0.1-schema-proposal/literal-fixtures.json",
        "schema_oracle_sha256": _sha(raw),
        "vectors": vectors,
    }


def _authority_locks() -> dict[str, object]:
    authorities = []
    for path, length, digest in AUTHORITY_LOCKS:
        raw = (ROOT / path).read_bytes()
        if len(raw) != length or _sha(raw) != digest:
            raise ValueError(f"immutable upstream authority drift: {path}")
        authorities.append({"length": length, "path": path, "sha256": digest})
    return {
        "accepted_baseline_commit": "0849b986d065105441e116dce15294250a323926",
        "authorities": authorities,
        "authority": "WP8 Task 7 immutable upstream authority locks",
        "core_v02_artifact_count": 110,
        "federation_object_count": 18,
        "format_version": 1,
        "schema_literal_count": 28,
        "task6_scenario_count": 4,
        "threshold_evidence_capability": 6,
        "threshold_literal_count": 89,
    }


def _signed_vectors() -> dict[str, object]:
    vectors: list[dict[str, object]] = []
    schema = json.loads((ROOT / "vectors/federation-v0.1-schema-proposal/literal-fixtures.json").read_bytes())
    accepted = [item for item in schema["fixtures"] if item["expected_outcome"] == "ACCEPT"]
    for value, fixture in enumerate(accepted, 1):
        name = fixture["object_type"]
        payload = bytes.fromhex(fixture["canonical_cbor_hex"])
        message = sign1(payload, KID, KEY)
        vectors.append(
            {
                "case": "valid-sign1",
                "cose_sign1_hex": message.hex(),
                "dependencies": [f"schema-oracle-{fixture['name']}"],
                "expected": "ACCEPT",
                "expected_reason": "NONE",
                "fixed_context": _fixed_context(),
                "id": f"signed-{value:02d}-{fixture['name']}",
                "kid_hex": KID.hex(),
                "mutation": False,
                "object_class": name,
                "payload_sha256": _sha(payload),
                "purpose": value if value <= 14 else 13,
                "signer_operator_id": _sha(f"operator-{value}".encode()),
                "threshold_envelope": None,
            }
        )
    defects = (
        ("malformed-cose", "ERR_PARSE"),
        ("invalid-signature", "ERR_SIGNATURE_INVALID"),
        ("wrong-kid", "ERR_IDENTITY"),
        ("wrong-key-purpose", "ERR_KEY_PURPOSE"),
    )
    for index, (case, reason) in enumerate(defects):
        payload = encode_deterministic({0: index + 1})
        signing_kid = b"wrong-kid" if case == "wrong-kid" else KID
        message = bytearray(sign1(payload, signing_kid, KEY))
        if case == "malformed-cose":
            message = message[:-1]
        elif case == "invalid-signature":
            message[-1] ^= 1
        vectors.append(
            {
                "case": case,
                "cose_sign1_hex": bytes(message).hex(),
                "dependencies": [],
                "expected": "REJECT",
                "expected_reason": reason,
                "fixed_context": _fixed_context(),
                "id": f"signed-negative-{case}",
                "actual_purpose": 1,
                "authority_context": {"expected_key_purpose": 9, "registered_key_purpose": 1}
                if case == "wrong-key-purpose"
                else {"expected_key_purpose": 1, "registered_key_purpose": 1},
                "expected_purpose": 9 if case == "wrong-key-purpose" else 1,
                "kid_hex": signing_kid.hex(),
                "mutation": False,
                "object_class": OBJECTS[index],
                "payload_sha256": _sha(payload),
                "purpose": 0 if case == "wrong-key-purpose" else 1,
                "signer_operator_id": _sha(b"negative-operator"),
                "threshold_envelope": None,
            }
        )
    coverage = [
        {
            "object_class": name,
            "vector_ids": [item["id"] for item in vectors if item["object_class"] == name],
            "authentication": "single-sign1" if any(item["object_class"] == name for item in vectors) else "threshold-or-semantic-context",
        }
        for name in OBJECTS
    ]
    return {
        "authority": "Federation v0.1 signed conformance vectors",
        "fixed_private_key_hex": "1f" * 32,
        "format_version": 1,
        "object_coverage": coverage,
        "valid_kid_hex": KID.hex(),
        "vectors": vectors,
    }


def _threshold_vectors() -> dict[str, object]:
    path = ROOT / "vectors/federation-v0.1-threshold-container/literal-fixtures.json"
    raw = path.read_bytes()
    oracle = json.loads(raw)
    vectors = []
    for index, item in enumerate(oracle["fixtures"], 1):
        vectors.append(
            {
                **item,
                "dependencies": [],
                "enforcement": "NONE" if item["expected_decision"] == "ACCEPT" else "DENY_NEW_USE",
                "fixed_time": FIXED_TIME,
                "id": f"threshold-{index:03d}-{item['name']}",
                "provenance": "specification-authored",
                "resource_expectation": "bounded-by-threshold-container-v1",
            }
        )
    return {
        "authority": "approved immutable threshold-container v1 literal oracle",
        "format_version": 1,
        "oracle_count": len(vectors),
        "oracle_path": "../federation-v0.1-threshold-container/literal-fixtures.json",
        "oracle_sha256": _sha(raw),
        "vectors": vectors,
    }


def _capability_vectors() -> dict[str, object]:
    cases = (
        ("valid-threshold-evidence", "ACCEPT", "NONE"),
        ("threshold-evidence-absent", "REJECT", "ERR_UNSUPPORTED_CRITICAL"),
        ("capability-stripped", "REJECT", "ERR_DOWNGRADE"),
        ("duplicate-capability", "REJECT", "ERR_SCHEMA"),
        ("unknown-critical-capability", "REJECT", "ERR_UNSUPPORTED_CRITICAL"),
        ("unsupported-capability", "REJECT", "ERR_UNSUPPORTED_CRITICAL"),
        ("wrong-capability-set-digest", "REJECT", "ERR_DOWNGRADE"),
        ("wrong-authenticated-transcript-digest", "REJECT", "ERR_REPLAY"),
        ("wrong-selected-core-version", "REJECT", "ERR_VERSION"),
        ("wrong-federation-version", "REJECT", "ERR_VERSION"),
        ("wrong-profile", "REJECT", "ERR_VERSION"),
        ("different-session-replay", "REJECT", "ERR_REPLAY"),
    )
    vectors = []
    for index, (case, outcome, reason) in enumerate(cases, 1):
        offered = [6]
        agreed = [6]
        selected_core, selected_federation, profile = "core-v0.2", "federation-v0.1", PROFILE
        if case == "threshold-evidence-absent":
            offered = agreed = []
        elif case == "capability-stripped":
            agreed = []
        elif case == "duplicate-capability":
            agreed = [6, 6]
        elif case in {"unknown-critical-capability", "unsupported-capability"}:
            agreed = [6, 7]
        elif case == "wrong-selected-core-version":
            selected_core = "core-v0.1"
        elif case == "wrong-federation-version":
            selected_federation = "federation-v0.2"
        elif case == "wrong-profile":
            profile = "federation-v0.1-other"
        session = _sha(f"authenticated-session-{index}".encode())
        offer_bytes = encode_deterministic({1: offered, 2: session.encode("ascii")})
        selection = {1: agreed, 2: selected_core, 3: selected_federation, 4: profile, 5: session}
        selection_bytes = encode_deterministic(selection)
        cap_digest = _sha(encode_deterministic(agreed))
        transcript = _sha(offer_bytes + selection_bytes)
        context = _sha(bytes.fromhex(cap_digest) + bytes.fromhex(transcript) + bytes.fromhex(session) + b"threshold-evidence-v1")
        vector = {
            "agreed_capabilities": agreed,
            "offered_capabilities": offered,
            "selected_core": selected_core,
            "selected_federation": selected_federation,
            "profile": profile,
            "authenticated_session_digest": session,
            "offer_cbor_hex": offer_bytes.hex(),
            "offer_sign1_hex": sign1(offer_bytes, b"cap-offer", KEY).hex(),
            "selection_cbor_hex": selection_bytes.hex(),
            "selection_sign1_hex": sign1(selection_bytes, b"cap-select", KEY).hex(),
            "authenticated_transcript_digest": transcript,
            "capability_set_digest": cap_digest,
            "case": case,
            "dependencies": [],
            "enforcement": "NONE" if outcome == "ACCEPT" else "DENY_NEW_USE",
            "expected_outcome": outcome,
            "expected_reason": reason,
            "fixed_time": FIXED_TIME,
            "id": f"capability-{index:02d}-{case}",
            "mutation": outcome == "ACCEPT",
            "threshold_signature_context_digest": context,
        }
        if case == "wrong-capability-set-digest":
            vector["capability_set_digest"] = "00" * 32
        elif case in {"wrong-authenticated-transcript-digest", "different-session-replay"}:
            vector["authenticated_transcript_digest"] = "11" * 32
        signed_context = bytes.fromhex(vector["threshold_signature_context_digest"])
        vector["signed_threshold_signature_context_hex"] = signed_context.hex()
        vector["threshold_evidence_sign1_hex"] = sign1(signed_context, b"threshold-context", KEY).hex()
        vectors.append(vector)
    valid = vectors[0]
    replay = vectors[-1]
    replay["replay_source_id"] = valid["id"]
    replay["signed_threshold_signature_context_hex"] = valid["signed_threshold_signature_context_hex"]
    replay["threshold_evidence_sign1_hex"] = valid["threshold_evidence_sign1_hex"]
    return {
        "authority": "authenticated Federation capability agreement",
        "fixed_private_key_hex": "1f" * 32,
        "format_version": 1,
        "required_capability": {"id": 6, "name": "THRESHOLD_EVIDENCE"},
        "vectors": vectors,
    }


def _scenarios() -> dict[str, object]:
    names = (
        "operator-registration",
        "operator-activation",
        "key-authorization",
        "key-rotation",
        "name-ownership-genesis",
        "ownership-transfer",
        "delegation",
        "sub-delegation",
        "trust-bundle-genesis",
        "trust-bundle-update",
        "checkpoint-genesis",
        "inclusion-proof",
        "consistency-proof",
        "witness-threshold",
        "endpoint-discovery",
        "source-authorization",
        "destination-authorization",
        "bilateral-success",
        "federation-authorization-context-creation",
        "accepted-route-authority",
        "replay-rejection",
        "key-revocation",
        "delegation-revocation",
        "selective-invalidation",
        "terminal-tombstone",
        "restart-and-replay-persistence",
        "rollback-rejection",
        "equivocation-quarantine",
        "checkpoint-stale-synchronization",
        "split-view-quarantine",
        "fresh-lkg",
        "restricted-degraded-mode",
        "hard-maximum-staleness-denial",
        "static-recovery",
        "static-recovery-expiry",
        "operator-suspension-quarantine",
        "continuity-preserving-recovery",
        "lineage-breaking-recovery",
        "conflict-resolution",
        "appeal-without-automatic-restoration",
        "threshold-capability-negotiation-success",
        "threshold-capability-downgrade-rejection",
        "cross-session-threshold-replay-rejection",
    )
    failures = {
        29: ReasonCode.ERR_CHECKPOINT,
        30: ReasonCode.ERR_SPLIT_VIEW,
        38: ReasonCode.ERR_RECOVERY_INVALID,
        40: ReasonCode.ERR_LOCAL_POLICY,
        42: ReasonCode.ERR_DOWNGRADE,
        43: ReasonCode.ERR_REPLAY,
    }
    policy = StaticRecoveryPolicy(
        b"P" * 32, (b"A" * 32, b"B" * 32), b"S" * 32, "static:route", ("control-outage",), FIXED_TIME - 1_000, FIXED_TIME + 1_000
    )
    state = FederationState.empty(static_policies=(policy,))
    accepted_events: dict[int, FederationEvent] = {}
    event_vectors: list[dict[str, object]] = []
    scenarios: list[dict[str, object]] = []

    def event_json(event: FederationEvent) -> dict[str, object]:
        return {
            "authority_expansion": event.authority_expansion,
            "compromised": event.compromised,
            "dependencies": [value.hex() for value in event.dependencies],
            "generation": event.generation,
            "key": event.key,
            "object_digest": event.object_digest.hex(),
            "object_kind": event.object_kind,
            "operation": event.operation,
            "operator_id": event.operator_id.hex(),
            "outage_trigger": event.outage_trigger,
            "peer_operator_id": event.peer_operator_id.hex(),
            "previous_digest": None if event.previous_digest is None else event.previous_digest.hex(),
            "recovery_of": event.recovery_of,
            "replay_digest": None if event.replay_digest is None else event.replay_digest.hex(),
            "requires_prior_authority": event.requires_prior_authority,
            "sequence": event.sequence,
            "service_id": event.service_id.hex(),
            "source_fresh_at": event.source_fresh_at,
            "static_policy_digest": None if event.static_policy_digest is None else event.static_policy_digest.hex(),
            "terminal": event.terminal,
            "valid_until": event.valid_until,
            "validation_failures": [value.name for value in event.validation_failures],
        }

    for ordinal, name in enumerate(names, 1):
        now = FIXED_TIME + ordinal
        event = FederationEvent(
            f"event:{ordinal:02d}",
            1,
            1,
            hashlib.sha256(f"object:{ordinal}".encode()).digest(),
            name,
            b"A" * 32,
            b"B" * 32,
            b"S" * 32,
            source_fresh_at=now,
        )
        if ordinal == 20:
            event = replace(event, replay_digest=b"R" * 32)
        elif ordinal == 21:
            event = replace(event, replay_digest=b"R" * 32)
        elif ordinal in {22, 23}:
            event = replace(event, compromised=True, dependencies=(b"D" * 32,))
        elif ordinal == 25:
            event = replace(event, terminal=True)
        elif ordinal == 27:
            base = accepted_events[26]
            event = replace(base, sequence=0)
        elif ordinal in {28, 30, 36}:
            base = accepted_events[{28: 26, 30: 24, 36: 25}[ordinal]]
            event = replace(base, object_digest=hashlib.sha256(f"conflict:{ordinal}".encode()).digest())
        elif ordinal == 31:
            event = replace(event, source_fresh_at=now - FederationProfile.trust_freshness_seconds + 10)
        elif ordinal in {32, 33}:
            base = accepted_events[31]
            event = replace(base, operation="existing_context")
            now = base.source_fresh_at + (
                FederationProfile.trust_freshness_seconds + 1 if ordinal == 32 else FederationProfile.degraded_staleness_seconds + 1
            )
        elif ordinal == 34:
            event = FederationEvent(
                "static:route",
                1,
                1,
                b"G" * 32,
                name,
                b"A" * 32,
                b"B" * 32,
                b"S" * 32,
                operation="static_recovery",
                static_policy_digest=policy.policy_digest,
                outage_trigger="control-outage",
            )
        elif ordinal == 35:
            event = FederationEvent(
                "static:route",
                1,
                1,
                b"H" * 32,
                name,
                b"A" * 32,
                b"B" * 32,
                b"S" * 32,
                operation="static_recovery",
                static_policy_digest=policy.policy_digest,
                outage_trigger="control-outage",
            )
            now = policy.expires_at + 1
        elif ordinal in failures:
            event = replace(event, validation_failures=(failures[ordinal],))
        pre_digest = state.digest.hex()
        successor, result = state.apply(event, now)
        if result.outcome.name == "ACCEPT" and result.state_changed:
            accepted_events[ordinal] = event
        event_id = f"state-event-{ordinal:02d}-{name}"
        event_vectors.append({"evaluation_time": now, "federation_event": event_json(event), "id": event_id})
        retained_state = {
            "accepted": [{"digest": item.object_digest.hex(), "key": item.key} for item in successor.accepted],
            "quarantine": [[key, [value.hex() for value in values]] for key, values in successor.quarantine],
            "tombstones": list(successor.tombstones),
        }
        scenarios.append(
            {
                "dependencies": [pre_digest],
                "effects": {
                    "quarantine": bool(successor.quarantine),
                    "retained_state": retained_state,
                    "revocation": ordinal in {22, 23},
                    "tombstone": bool(successor.tombstones),
                },
                "emitted_evidence": [value.hex() for value in result.emitted],
                "enforcement": result.enforcement.name,
                "evaluation_time": now,
                "expected_reason": result.reason.name,
                "expected_result": result.outcome.name,
                "id": name,
                "input": {
                    "artifact": "stateful-scenarios.json",
                    "fixed_nonce": f"{ordinal:032x}",
                    "operation": name,
                    "pre_state": pre_digest,
                    "vector_id": event_id,
                },
                "mutation": result.state_changed,
                "ordinal": ordinal,
                "resulting_state_digest": successor.digest.hex(),
            }
        )
        state = successor
    oracle_path = ROOT / "tests/federation/fixtures/task6-state-scenarios.json"
    raw = oracle_path.read_bytes()
    return {
        "authority": "Federation v0.1 ordered stateful scenarios",
        "event_vectors": event_vectors,
        "format_version": 1,
        "scenarios": scenarios,
        "task6_oracle": json.loads(raw)["scenarios"],
        "task6_oracle_sha256": _sha(raw),
        "task6_oracle_path": "../../tests/federation/fixtures/task6-state-scenarios.json",
    }


def _precedence() -> dict[str, object]:
    entries = (
        ("resource-parsing", "ERR_RESOURCE_LIMIT"),
        ("canonical-encoding", "ERR_NON_CANONICAL"),
        ("crypto-signature", "ERR_SIGNATURE_INVALID"),
        ("identity-key-lifecycle", "ERR_IDENTITY"),
        ("schema-version", "ERR_SCHEMA"),
        ("authority-scope", "ERR_AUTHORITY"),
        ("generation-sequence-continuity", "ERR_ROLLBACK"),
        ("revocation-terminal", "ERR_REVOKED"),
        ("transparency-witness", "ERR_TRANSPARENCY"),
        ("freshness-outage", "ERR_FRESHNESS"),
        ("local-authorization", "ERR_LOCAL_POLICY"),
    )
    precedence = [{"class": name, "rank": rank, "reason": reason} for rank, (name, reason) in enumerate(entries, 1)]
    reasons = [item["reason"] for item in precedence]
    vectors = [
        {
            "defects": [reasons[index], reasons[-1]],
            "expected_reason": reasons[index],
            "id": f"precedence-{index + 1:02d}",
            "rank_pair": [index + 1, 11],
        }
        for index in range(10)
    ]
    vectors.append(
        {"defects": reasons, "expected_reason": reasons[0], "id": "precedence-all-simultaneous", "rank_pair": list(range(1, 12))}
    )
    return {"authority": "Federation v0.1 exact error precedence", "format_version": 1, "precedence": precedence, "vectors": vectors}


def _readme() -> bytes:
    return (
        "# Federation v0.1 Development Profile conformance vectors\n\n"
        "This closed package is the normative deterministic cross-language test authority for the approved Federation v0.1 Development Profile. "
        "It binds static and signed objects, threshold-container v1 literals, capability agreement, ordered state transitions, exact decisions, symbolic reasons, enforcement, mutation, state digests, dependencies, fixed times, and resource expectations.\n\n"
        "The 28 Task 2 schema literals, Task 6 specification-authored state manifest, and 89 threshold-container literals remain independent oracles. "
        "Generation verifies and references their bytes; disagreement fails and never rewrites them. `THRESHOLD_EVIDENCE = 6` is required and `FEDERATION_OBJECTS` alone is insufficient.\n\n"
        "Run `python scripts/generate_federation_v01_vectors.py --check vectors/federation-v0.1`. Check mode is read-only.\n\n"
        "## Non-claims\n\nThis package does not claim independent Node or Go verification, live federation deployment, production governance, live DNS/HTTPS, remote verification, or real-world threshold custody. Those are outside Task 7.\n"
    ).encode("ascii")


def build_package() -> dict[str, bytes]:
    artifacts = {
        "README.md": _readme(),
        "authority-locks.json": _json(_authority_locks()),
        "capability-vectors.json": _json(_capability_vectors()),
        "error-precedence.json": _json(_precedence()),
        "signed-vectors.json": _json(_signed_vectors()),
        "stateful-scenarios.json": _json(_scenarios()),
        "static-vectors.json": _json(_static_vectors()),
        "threshold-vectors.json": _json(_threshold_vectors()),
    }
    classes = {
        "README.md": "documentation",
        "authority-locks.json": "immutable-authority",
        "capability-vectors.json": "capability",
        "error-precedence.json": "precedence",
        "signed-vectors.json": "signed-object",
        "stateful-scenarios.json": "stateful-scenario",
        "static-vectors.json": "static-object",
        "threshold-vectors.json": "threshold-envelope",
    }
    entries = []
    for index, path in enumerate(sorted(artifacts), 1):
        data = artifacts[path]
        entries.append(
            {
                "class": classes[path],
                "dependencies": [],
                "enforcement": None,
                "expected_outcome": None,
                "expected_reason": None,
                "expected_state_digest": None,
                "federation_version": "federation-v0.1",
                "fixed_time": FIXED_TIME,
                "id": f"artifact-{index:02d}-{path.rsplit('.', 1)[0]}",
                "length": len(data),
                "mutation": False,
                "path": path,
                "profile": PROFILE,
                "sha256": _sha(data),
            }
        )
    manifest = {
        "artifacts": entries,
        "authority": "WP8 Task 7 deterministic Federation v0.1 conformance package",
        "format_version": 1,
        "package": "federation-v0.1",
        "package_version": PACKAGE_VERSION,
    }
    artifacts["manifest.json"] = _json(manifest)
    return artifacts


def validate_manifest(manifest: dict[str, object], package: Path) -> None:
    top_fields = {"artifacts", "authority", "format_version", "package", "package_version"}
    entry_fields = {
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
    if (
        not isinstance(manifest, dict)
        or set(manifest) != top_fields
        or manifest.get("format_version") != 1
        or manifest.get("package_version") != PACKAGE_VERSION
    ):
        raise ValueError("unsupported package version")
    if manifest.get("package") != "federation-v0.1" or not isinstance(manifest.get("authority"), str):
        raise ValueError("invalid package authority")
    entries = manifest.get("artifacts")
    if not isinstance(entries, list):
        raise ValueError("manifest artifacts must be a list")
    ids: set[str] = set()
    paths: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("manifest entry must be an object")
        if set(entry) != entry_fields:
            raise ValueError("unknown or missing manifest entry field")
        identifier, raw_path = entry.get("id"), entry.get("path")
        if not isinstance(identifier, str) or not identifier or identifier in ids:
            raise ValueError("duplicate or invalid artifact ID")
        if not isinstance(raw_path, str) or not raw_path or "\\" in raw_path or raw_path == "manifest.json":
            raise ValueError("unsafe artifact path")
        path = PurePosixPath(raw_path)
        if path.is_absolute() or len(path.parts) != 1 or any(part in {"", ".", ".."} for part in path.parts) or raw_path in paths:
            raise ValueError("unsafe or duplicate artifact path")
        ids.add(identifier)
        paths.add(raw_path)
        candidate = package / raw_path
        if candidate.is_symlink() or not candidate.is_file():
            raise ValueError("listed artifact is missing or unsafe")
        raw = candidate.read_bytes()
        if (
            type(entry["length"]) is not int
            or entry["length"] < 0
            or entry["length"] != len(raw)
            or type(entry["sha256"]) is not str
            or len(entry["sha256"]) != 64
            or entry["sha256"] != _sha(raw)
        ):
            raise ValueError("artifact length or digest mismatch")
        if type(entry["class"]) is not str or not entry["class"]:
            raise ValueError("artifact class is invalid")
        for field in ("enforcement", "expected_outcome", "expected_reason"):
            if entry[field] is not None and (type(entry[field]) is not str or not entry[field]):
                raise ValueError("artifact expectation is invalid")
        state_digest = entry["expected_state_digest"]
        if state_digest is not None and (type(state_digest) is not str or len(state_digest) != 64):
            raise ValueError("artifact state digest is invalid")
        if (entry["federation_version"], entry["profile"]) != ("federation-v0.1", PROFILE):
            raise ValueError("artifact version or profile mismatch")
        if type(entry["fixed_time"]) is not int or type(entry["mutation"]) is not bool:
            raise ValueError("artifact expectation type mismatch")
    descendants = list(package.rglob("*"))
    if any(item.is_symlink() or item.is_dir() for item in descendants):
        raise ValueError("manifest package contains an unlisted directory or symlink")
    actual = {item.relative_to(package).as_posix() for item in descendants if item.is_file() and item.name != "manifest.json"}
    if actual != paths:
        raise ValueError("manifest is not closed over package files")
    known = ids
    graph: dict[str, list[str]] = {}
    for entry in entries:
        dependencies = entry.get("dependencies")
        if (
            not isinstance(dependencies, list)
            or len(dependencies) != len(set(dependencies))
            or any(type(dep) is not str or dep not in known or dep == entry["id"] for dep in dependencies)
        ):
            raise ValueError("missing or cyclic artifact dependency")
        graph[entry["id"]] = dependencies
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str) -> None:
        if node in visiting:
            raise ValueError("cyclic artifact dependency")
        if node in visited:
            return
        visiting.add(node)
        for dependency in graph[node]:
            visit(dependency)
        visiting.remove(node)
        visited.add(node)

    for node in graph:
        visit(node)


def verify_package(path: Path) -> list[str]:
    expected = build_package()
    if path.is_symlink() or not path.is_dir():
        return [f"package directory missing: {path}"]
    actual_paths = {item.relative_to(path).as_posix() for item in path.rglob("*") if item.is_file()}
    errors = (
        [f"unlisted or missing files: expected {sorted(expected)}, got {sorted(actual_paths)}"] if actual_paths != set(expected) else []
    )
    for name, data in expected.items():
        candidate = path / name
        if candidate.is_symlink():
            errors.append(f"unsafe artifact symlink: {name}")
            continue
        if not candidate.is_file():
            continue
        actual = candidate.read_bytes()
        if actual != data:
            errors.append(f"artifact mismatch: {name}")
    try:
        manifest = json.loads((path / "manifest.json").read_bytes())
        validate_manifest(manifest, path)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        errors.append(f"manifest invalid: {exc}")
    return errors


def write_package(path: Path) -> None:
    if path.is_symlink():
        raise ValueError("package directory must not be a symlink")
    path.mkdir(parents=True, exist_ok=True)
    expected = build_package()
    for existing in path.rglob("*"):
        if existing.is_symlink():
            raise ValueError(f"refusing package symlink: {existing.name}")
        if existing.is_file() and existing.relative_to(path).as_posix() not in expected:
            raise ValueError(f"refusing to overwrite open package containing {existing.name}")
    for name, data in expected.items():
        (path / name).write_bytes(data)
