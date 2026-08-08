from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from nbsr.protocol.cbor import decode_deterministic, encode_deterministic
from nbsr.protocol.cose import sign1
from nbsr.protocol.errors import ProtocolViolation
from nbsr.federation.identity import OperatorId
from nbsr.federation.ownership import derive_service_id


ROOT = Path(__file__).resolve().parents[2]
CORE_V02 = ROOT / "vectors" / "core-v0.2"
PROFILE_ID = "nbsr-federation-dev-v1"


class F75VectorError(ValueError):
    """The additive F75 body or binding is invalid."""


def _federation_context_bytes() -> bytes:
    service_id = derive_service_id(b"S" * 32, "service.example")
    authority_proof_digest = hashlib.sha256(_authority_proof_bytes()).digest()
    dependencies = [
        [1, b"a" * 32],
        [3, b"b" * 32],
        [5, b"B" * 32],
        [6, b"C" * 32],
        [11, authority_proof_digest],
    ]
    scope = {
        1: "service.example",
        2: service_id,
        3: None,
        4: b"S" * 32,
        5: b"D" * 32,
        6: "eu",
        7: [[8443, 8443]],
        8: [6],
        9: [1],
        10: False,
        11: 0,
    }
    payload = {
        1: 12,
        2: 1,
        3: {1: 9, 2: b"S" * 32, 3: b"auth", 4: b"S" * 32},
        9: 1_893_455_940,
        32: b"context",
        33: b"S" * 32,
        34: b"D" * 32,
        35: service_id,
        36: authority_proof_digest,
        37: b"B" * 32,
        38: b"C" * 32,
        39: b"P" * 32,
        40: scope,
        41: 1_893_456_300,
        42: 1,
        43: 7,
        44: dependencies,
        45: hashlib.sha256(encode_deterministic(dependencies)).digest(),
        46: b"R" * 32,
    }
    return encode_deterministic(payload)


def _authority_proof_bytes() -> bytes:
    service_id = derive_service_id(b"S" * 32, "service.example")
    # This is the approved service-bound proof. Its independent scope remains a
    # proof fixture; the route's effective service scope is authenticated by the
    # FederationAuthorizationContext below.
    proof_scope = {
        1: "service.example", 2: b"V" * 32, 3: None, 4: b"S" * 32,
        5: b"D" * 32, 6: "eu", 7: [[443, 443]], 8: [6], 9: [1], 10: False, 11: 0,
    }
    return encode_deterministic({
        1: 11, 2: 1, 32: b"proof", 33: b"A" * 32,
        34: [b"1" * 32, b"2" * 32], 35: service_id, 36: proof_scope,
        37: b"S" * 32, 38: b"D" * 32, 39: b"B" * 32,
        40: b"C" * 32, 41: b"R" * 32, 42: 1_893_456_300,
    })


def _positive_parts() -> tuple[dict[int, object], list[object], bytes]:
    envelope = decode_deterministic((CORE_V02 / "artifacts/valid/envelopes/route-open.cbor").read_bytes())
    body = envelope[5]
    original_cose = decode_deterministic(body[2][1:])
    claims = decode_deterministic(original_cose[2])
    claims[4] = OperatorId(b"S" * 32).text
    claims[6] = OperatorId(b"D" * 32).text
    grant_seed = bytes.fromhex(
        (CORE_V02 / "keys/test-only-route-grant-ed25519-seed.hex").read_text(encoding="ascii").strip()
    )
    route_grant = sign1(
        encode_deterministic(claims),
        b"nbsr-test-route-grant-key",
        Ed25519PrivateKey.from_private_bytes(grant_seed),
    )
    route_grant_digest = hashlib.sha256(route_grant).digest()
    federation_context_digest = hashlib.sha256(_federation_context_bytes()).digest()
    binding = {
        0: 1,
        1: 1,
        2: 1,
        3: PROFILE_ID,
        4: route_grant_digest,
        5: federation_context_digest,
    }
    transcript = [
        "NBSR-FED-ROUTE-OPEN",
        2,
        2,
        [1, 1, 1, PROFILE_ID],
        envelope[3],
        envelope[2],
        body[1],
        claims[1],
        claims[7][0],
        body[3],
        body[4],
        claims[3],
        body[5],
        route_grant_digest,
        body[6],
        federation_context_digest,
    ]
    return binding, transcript, route_grant


def validate_f75_route_authority(body: dict[int, object], context_wire: bytes) -> None:
    try:
        context = decode_deterministic(context_wire)
        sign1_body = decode_deterministic(body[2][1:])
        claims = decode_deterministic(sign1_body[2])
        requested_transport = body[4]
        requested_port = body[5]
        scope = context[40]
        scoped_transport = 6 if requested_transport == "tcp" else 17 if requested_transport == "udp" else None
        in_context = scoped_transport in scope[8] and any(start <= requested_port <= end for start, end in scope[7])
        in_grant = requested_transport in claims[8] and requested_port in claims[9]
    except (KeyError, TypeError, ProtocolViolation) as exc:
        raise F75VectorError("F75 route authority is malformed") from exc
    if not in_context or not in_grant:
        raise F75VectorError("Federation context, RouteGrant, and ROUTE_OPEN service authority disagree")


def validate_f75_authority_proof(context_wire: bytes, proof_wire: bytes) -> None:
    try:
        context = decode_deterministic(context_wire)
        proof = decode_deterministic(proof_wire)
    except ProtocolViolation as exc:
        raise F75VectorError("F75 authority proof is malformed") from exc
    if (
        type(context) is not dict or type(proof) is not dict
        or context.get(35) != proof.get(35)
        or context.get(36) != hashlib.sha256(proof_wire).digest()
    ):
        raise F75VectorError("F75 authority proof is not bound to the accepted service")


def validate_f75_route_time(body: dict[int, object], context_wire: bytes, proof_wire: bytes) -> None:
    try:
        context = decode_deterministic(context_wire)
        proof = decode_deterministic(proof_wire)
        claims = decode_deterministic(decode_deterministic(body[2][1:])[2])
        opened_at = body[6]
    except (KeyError, TypeError, ProtocolViolation) as exc:
        raise F75VectorError("F75 validity authority is malformed") from exc
    if not (
        context[9] <= opened_at <= context[41]
        and opened_at <= proof[42]
        and claims[11] <= opened_at <= claims[12]
    ):
        raise F75VectorError("F75 route establishment is outside authenticated validity")


def build_positive_vector() -> dict[str, object]:
    binding, transcript, route_grant = _positive_parts()
    route_grant_digest = hashlib.sha256(route_grant).digest()
    federation_context_digest = transcript[15]
    transcript_bytes = encode_deterministic(transcript)
    seed = bytes.fromhex((CORE_V02 / "keys/test-only-session-ed25519-seed.hex").read_text(encoding="ascii").strip())
    signature = Ed25519PrivateKey.from_private_bytes(seed).sign(transcript_bytes)
    envelope = decode_deterministic((CORE_V02 / "artifacts/valid/envelopes/route-open.cbor").read_bytes())
    body = dict(envelope[5])
    body[0] = 2
    body[2] = route_grant
    body[7] = signature
    body[8] = binding
    validate_f75_route_authority(body, _federation_context_bytes())
    validate_f75_authority_proof(_federation_context_bytes(), _authority_proof_bytes())
    validate_f75_route_time(body, _federation_context_bytes(), _authority_proof_bytes())
    return {
        "route_grant_digest": route_grant_digest.hex(),
        "federation_context_digest": federation_context_digest.hex(),
        "binding_hex": encode_deterministic(binding).hex(),
        "transcript_hex": transcript_bytes.hex(),
        "signature_hex": signature.hex(),
        "body_hex": encode_deterministic(body).hex(),
        "transcript_item_count": len(transcript),
    }


def decode_f75_body(wire: bytes, *, expected_context_digest: bytes) -> dict[int, object]:
    if type(wire) is not bytes or type(expected_context_digest) is not bytes or len(expected_context_digest) != 32:
        raise F75VectorError("invalid F75 verification context")
    try:
        value = decode_deterministic(wire)
    except ProtocolViolation as exc:
        raise F75VectorError("invalid deterministic F75 CBOR") from exc
    if type(value) is not dict or set(value) != set(range(9)) or value.get(0) != 2:
        raise F75VectorError("ROUTE_OPEN v2 must contain exactly keys 0 through 8")
    binding = value[8]
    if type(binding) is not dict or set(binding) != set(range(6)):
        raise F75VectorError("federation binding must contain exactly keys 0 through 5")
    if (
        type(binding[0]) is not int
        or binding[0] != 1
        or type(binding[1]) is not int
        or binding[1] != 1
        or type(binding[2]) is not int
        or binding[2] != 1
        or type(binding[3]) is not str
        or binding[3] != PROFILE_ID
        or type(binding[4]) is not bytes
        or len(binding[4]) != 32
        or type(binding[5]) is not bytes
        or len(binding[5]) != 32
    ):
        raise F75VectorError("federation binding version, profile, or digest is invalid")
    route_grant = value[2]
    if type(route_grant) is not bytes or hashlib.sha256(route_grant).digest() != binding[4]:
        raise F75VectorError("RouteGrant digest does not match exact carried bytes")
    if binding[5] != expected_context_digest:
        raise F75VectorError("Federation context digest does not match accepted authority")
    return value


def build_mutation_vectors() -> list[dict[str, str]]:
    _, positive, _ = _positive_parts()
    mutations: list[tuple[str, tuple[int, ...], object]] = [
        ("domain-separator", (0,), "NBSR-FED-ROUTE-OPEN-X"),
        ("core-version", (1,), 1),
        ("body-version", (2,), 1),
        ("binding-version", (3, 0), 2),
        ("extension-id", (3, 1), 2),
        ("extension-version", (3, 2), 2),
        ("profile-id", (3, 3), "nbsr-static-trust-v1"),
        ("session-id", (4,), b"x" * 16),
        ("request-id", (5,), b"x" * 16),
        ("channel-id", (6,), b"x" * 16),
        ("route-id", (7,), b"x" * 16),
        ("destination-edge", (8,), "other.edge"),
        ("edge-nonce", (9,), b"x" * 32),
        ("transport", (10,), "udp"),
        ("service", (11,), "other.example"),
        ("port", (12,), 443),
        ("route-grant-digest", (13,), b"x" * 32),
        ("opened-at", (14,), 1_893_456_001),
        ("federation-context-digest", (15,), b"x" * 32),
    ]
    result: list[dict[str, str]] = []
    for vector_id, path, replacement in mutations:
        candidate = deepcopy(positive)
        if len(path) == 1:
            candidate[path[0]] = replacement
        else:
            nested = candidate[path[0]]
            if type(nested) is not list:
                raise AssertionError("mutation path is not an array")
            nested[path[1]] = replacement
        result.append({"id": vector_id, "transcript_hex": encode_deterministic(candidate).hex()})
    return result


def _body_mutation_vectors() -> list[dict[str, str]]:
    positive = _positive_body_value()

    def encoded(vector_id: str, value: object) -> dict[str, str]:
        return {"id": vector_id, "body_hex": encode_deterministic(value).hex()}

    mutations: list[dict[str, str]] = []
    body = deepcopy(positive)
    body[0] = 1
    mutations.append(encoded("body-v1-with-key-8", body))
    body = deepcopy(positive)
    del body[8]
    mutations.append(encoded("body-v2-missing-key-8", body))
    for vector_id, key, replacement in (
        ("wrong-binding-version", 0, 2),
        ("wrong-extension-id", 1, 2),
        ("wrong-extension-version", 2, 2),
        ("wrong-profile-id", 3, "nbsr-static-trust-v1"),
        ("route-grant-digest-length", 4, b"x" * 31),
        ("context-digest-length", 5, b"x" * 31),
        ("route-grant-digest-mismatch", 4, b"x" * 32),
        ("context-digest-mismatch", 5, b"x" * 32),
    ):
        body = deepcopy(positive)
        body[8][key] = replacement
        mutations.append(encoded(vector_id, body))
    body = deepcopy(positive)
    body[8][6] = 1
    mutations.append(encoded("unknown-binding-key", body))
    body = deepcopy(positive)
    del body[8][5]
    mutations.append(encoded("missing-binding-key", body))
    body = deepcopy(positive)
    body[8] = b"not-a-map"
    mutations.append(encoded("malformed-binding-type", body))

    binding_wire = encode_deterministic(positive[8])
    canonical = encode_deterministic(positive)
    duplicate_binding = bytes([0xA7]) + binding_wire[1:] + b"\x00\x01"
    mutations.append(
        {
            "id": "duplicate-binding-key",
            "body_hex": (canonical[: canonical.rfind(binding_wire)] + duplicate_binding).hex(),
        }
    )
    mutations.append(
        {
            "id": "noncanonical-body-version",
            "body_hex": (canonical[:2] + b"\x18\x02" + canonical[3:]).hex(),
        }
    )
    if len(mutations) != 15:
        raise AssertionError("F75 body mutation inventory must contain exactly 15 vectors")
    return mutations


def _positive_body_value() -> dict[int, object]:
    value = decode_deterministic(bytes.fromhex(str(build_positive_vector()["body_hex"])))
    if type(value) is not dict:
        raise AssertionError("positive F75 body is not a map")
    return value


def build_package() -> dict[str, bytes]:
    positive = build_positive_vector()
    _, _, route_grant = _positive_parts()
    mutations = {
        "body": _body_mutation_vectors(),
        "transcript": build_mutation_vectors(),
    }
    readme = (
        "# WP8 Task 10 F75 ROUTE_OPEN v2 evidence\n\n"
        "This additive package freezes deterministic evidence for the approved federated "
        "ROUTE_OPEN v2 binding and 16-item proof-of-possession transcript. It does not "
        "modify the frozen Federation v0.1 Task 7 package or non-federated ROUTE_OPEN v1.\n"
    ).encode("utf-8")
    return {
        "README.md": readme,
        "federation-context.cbor": _federation_context_bytes(),
        "route-grant.cose": route_grant,
        "federation-binding.cbor": bytes.fromhex(str(positive["binding_hex"])),
        "route-open-body.cbor": bytes.fromhex(str(positive["body_hex"])),
        "transcript.cbor": bytes.fromhex(str(positive["transcript_hex"])),
        "signature.bin": bytes.fromhex(str(positive["signature_hex"])),
        "mutations.json": (json.dumps(mutations, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8"),
    }


def _manifest_for(package: dict[str, bytes]) -> bytes:
    artifacts = [
        {
            "length": len(content),
            "path": path,
            "sha256": hashlib.sha256(content).hexdigest(),
        }
        for path, content in sorted(package.items())
    ]
    manifest = {"artifacts": artifacts, "package": "wp8-f75-route-open", "version": 1}
    return (json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def write_package(root: Path, package: dict[str, bytes]) -> None:
    if set(package) != {
        "README.md",
        "federation-context.cbor",
        "route-grant.cose",
        "federation-binding.cbor",
        "route-open-body.cbor",
        "transcript.cbor",
        "signature.bin",
        "mutations.json",
    }:
        raise F75VectorError("F75 package inventory must contain exactly eight approved artifacts")
    root.mkdir(parents=True, exist_ok=True)
    for relative, content in package.items():
        path = root / relative
        path.write_bytes(content)
    (root / "manifest.json").write_bytes(_manifest_for(package))


def verify_package(root: Path) -> dict[str, int]:
    if not root.is_dir() or root.is_symlink():
        raise F75VectorError("F75 package root must be a real directory")
    files = [path for path in root.rglob("*") if path.is_file() or path.is_symlink()]
    if any(path.is_symlink() for path in files):
        raise F75VectorError("F75 package must not contain symlinks")
    try:
        manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise F75VectorError("F75 manifest is unreadable") from exc
    if type(manifest) is not dict or set(manifest) != {"artifacts", "package", "version"}:
        raise F75VectorError("F75 manifest schema is invalid")
    if manifest["package"] != "wp8-f75-route-open" or manifest["version"] != 1:
        raise F75VectorError("F75 manifest identity is invalid")
    artifacts = manifest["artifacts"]
    if type(artifacts) is not list or len(artifacts) != 8:
        raise F75VectorError("F75 manifest must list exactly eight artifacts")
    expected_files = {"manifest.json"}
    for entry in artifacts:
        if type(entry) is not dict or set(entry) != {"length", "path", "sha256"}:
            raise F75VectorError("F75 manifest artifact schema is invalid")
        relative = entry["path"]
        if type(relative) is not str or Path(relative).is_absolute() or Path(relative).parts != (relative,):
            raise F75VectorError("F75 manifest artifact path is invalid")
        expected_files.add(relative)
        content = (root / relative).read_bytes()
        if type(entry["length"]) is not int or entry["length"] != len(content):
            raise F75VectorError("F75 artifact length mismatch")
        if type(entry["sha256"]) is not str or entry["sha256"] != hashlib.sha256(content).hexdigest():
            raise F75VectorError("F75 artifact digest mismatch")
    actual_files = {path.relative_to(root).as_posix() for path in files}
    if actual_files != expected_files:
        raise F75VectorError("F75 package inventory is not closed")
    try:
        mutations = json.loads((root / "mutations.json").read_text(encoding="utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise F75VectorError("F75 mutations are unreadable") from exc
    transcript_count = len(mutations.get("transcript", [])) if type(mutations) is dict else -1
    body_count = len(mutations.get("body", [])) if type(mutations) is dict else -1
    if transcript_count != 19 or body_count != 15:
        raise F75VectorError("F75 mutation inventory is incomplete")
    positive = build_positive_vector()
    if (root / "transcript.cbor").read_bytes().hex() != positive["transcript_hex"]:
        raise F75VectorError("F75 transcript does not match the frozen positive literal")
    decode_f75_body(
        (root / "route-open-body.cbor").read_bytes(),
        expected_context_digest=bytes.fromhex(str(positive["federation_context_digest"])),
    )
    return {"artifacts": 8, "transcript_mutations": transcript_count, "body_mutations": body_count}
