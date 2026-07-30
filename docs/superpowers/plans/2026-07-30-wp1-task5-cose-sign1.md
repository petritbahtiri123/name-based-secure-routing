# WP1 Task 5 COSE Sign1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the frozen Core v0.1 tagged COSE Sign1 Ed25519 profile with explicit caller trust/error context and D6-A3 `kid` bindings.

**Architecture:** A focused `nbsr.protocol.cose` module uses the existing NBSR deterministic CBOR encoder/decoder and `cryptography` Ed25519 primitives. It handles only the exact preferred tag-18 wrapper, keeps the generic CBOR decoder tag-free, exposes no generic algorithm negotiation, and maps untrusted verification failures to the caller-selected record or grant error.

**Tech Stack:** Python 3.12/3.13 target, `cryptography>=44,<46`, existing `nbsr.protocol.cbor`, pytest, Ruff.

## Global Constraints

- Work only on `codex/nbsr-v3-wp0-wp1`; do not modify or merge `main`.
- Do not push without an explicit user request.
- Do not add or change dependencies.
- Do not change the 17 message codes, 19 error codes, D6 numeric schemas, frozen states/transitions, extension rules, or COSE wrapper set.
- Use only COSE Sign1 tag 18, EdDSA algorithm `-8`, Ed25519 keys, attached payload, and empty external AAD.
- Keep `kid` opaque `bytes` with length 1 through 64 and resolve it only in the caller-supplied mapping.
- Preserve `NBSR_E_OVER_CAPACITY` from the existing bounded CBOR gate.
- Add no runtime import, network operation, logging, telemetry, vector package, WP2, or WP3 integration.
- Preserve unrelated untracked paths `.codex-test-temp-w4/`, `.superpowers/`, and `docs/leakguard_phase19_qa_pack/`.

## File map

| File | Responsibility |
|---|---|
| `nbsr/protocol/cose.py` | Exact tag-18 encoding, Ed25519 signing/verification, bounded errors, and `kid` binding |
| `tests/protocol/test_cose.py` | Positive, structural, algorithm-confusion, trust, tamper, D6-A3, and resource tests |
| `tests/test_wp3_rust_transport_isolation.py` | Existing isolation test; must remain green and unchanged |

---

### Task 1: Freeze the public COSE boundary and deterministic signer

**Files:**
- Create: `tests/protocol/test_cose.py`
- Create: `nbsr/protocol/cose.py`

**Interfaces:**
- Consumes:
  - `encode_deterministic(value: object) -> bytes`
  - `ErrorCode`
  - `ProtocolViolation`
- Produces:
  - `VerifiedSign1(payload: bytes, kid: bytes)`
  - `sign1(payload: bytes, kid: bytes, key: Ed25519PrivateKey) -> bytes`

- [ ] **Step 1: Write the failing deterministic signing test**

Create the test key and assert exact stability:

```python
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from nbsr.protocol.cbor import decode_deterministic
from nbsr.protocol.cose import sign1

PRIVATE_KEY = Ed25519PrivateKey.from_private_bytes(bytes(range(32)))
KID = b"test-owner-key"
PAYLOAD = b"\xa1\x00\x01"


def test_sign1_is_deterministic_and_uses_exact_tagged_profile() -> None:
    first = sign1(PAYLOAD, KID, PRIVATE_KEY)
    second = sign1(PAYLOAD, KID, PRIVATE_KEY)

    assert first == second
    assert first[:1] == b"\xd2"
    body = decode_deterministic(first[1:])
    assert len(body) == 4
    assert decode_deterministic(body[0]) == {1: -8, 4: KID}
    assert body[1] == {}
    assert body[2] == PAYLOAD
    assert len(body[3]) == 64
```

- [ ] **Step 2: Run the focused test and confirm RED**

Run:

```powershell
python -m pytest -q tests/protocol/test_cose.py::test_sign1_is_deterministic_and_uses_exact_tagged_profile
```

Expected: nonzero because `nbsr.protocol.cose` does not exist.

- [ ] **Step 3: Implement the immutable result and minimum signer**

Create:

```python
from __future__ import annotations

from dataclasses import dataclass

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from nbsr.protocol.cbor import encode_deterministic
from nbsr.protocol.errors import ProtocolViolation
from nbsr.protocol.registry import ErrorCode


_TAG_18 = b"\xd2"
_ALGORITHM_EDDSA = -8


@dataclass(frozen=True, slots=True)
class VerifiedSign1:
    payload: bytes
    kid: bytes


def _profile_error() -> ProtocolViolation:
    return ProtocolViolation(
        ErrorCode.NBSR_E_PROFILE_UNSUPPORTED,
        "Unsupported COSE Sign1 profile",
    )


def _require_kid_value(kid: object) -> bytes:
    if type(kid) is not bytes or not 1 <= len(kid) <= 64:
        raise _profile_error()
    return kid


def sign1(
    payload: bytes,
    kid: bytes,
    key: Ed25519PrivateKey,
) -> bytes:
    if type(payload) is not bytes or not isinstance(key, Ed25519PrivateKey):
        raise _profile_error()
    checked_kid = _require_kid_value(kid)
    protected = encode_deterministic({1: _ALGORITHM_EDDSA, 4: checked_kid})
    to_be_signed = encode_deterministic(
        ["Signature1", protected, b"", payload]
    )
    signature = key.sign(to_be_signed)
    return _TAG_18 + encode_deterministic(
        [protected, {}, payload, signature]
    )
```

- [ ] **Step 4: Run the test and confirm GREEN**

Run:

```powershell
python -m pytest -q tests/protocol/test_cose.py::test_sign1_is_deterministic_and_uses_exact_tagged_profile
python -m ruff check nbsr/protocol/cose.py tests/protocol/test_cose.py
```

Expected: one passing test and Ruff exit 0.

- [ ] **Step 5: Commit Task 1**

```powershell
git add nbsr/protocol/cose.py tests/protocol/test_cose.py
git commit -m "feat(protocol): add deterministic COSE Sign1 signer"
```

---

### Task 2: Verify the exact profile in caller trust context

**Files:**
- Modify: `tests/protocol/test_cose.py`
- Modify: `nbsr/protocol/cose.py`

**Interfaces:**
- Consumes: Task 1 `VerifiedSign1` and exact tagged bytes.
- Produces:
  - `verify_sign1(message, keys, failure_code) -> VerifiedSign1`
  - accepted `failure_code` values are exactly
    `NBSR_E_RECORD_UNTRUSTED` and `NBSR_E_GRANT_INVALID`.

- [ ] **Step 1: Write valid verification and explicit error-context tests**

Add:

```python
import pytest

from nbsr.protocol.errors import ProtocolViolation
from nbsr.protocol.registry import ErrorCode
from nbsr.protocol.cose import verify_sign1


@pytest.mark.parametrize(
    "failure_code",
    (
        ErrorCode.NBSR_E_RECORD_UNTRUSTED,
        ErrorCode.NBSR_E_GRANT_INVALID,
    ),
)
def test_verify_sign1_uses_only_caller_trust_context(
    failure_code: ErrorCode,
) -> None:
    message = sign1(PAYLOAD, KID, PRIVATE_KEY)
    verified = verify_sign1(
        message,
        {KID: PRIVATE_KEY.public_key()},
        failure_code,
    )

    assert verified.payload == PAYLOAD
    assert verified.kid == KID

    with pytest.raises(ProtocolViolation) as missing:
        verify_sign1(message, {}, failure_code)
    assert missing.value.code is failure_code


def test_verify_sign1_rejects_invalid_failure_context() -> None:
    message = sign1(PAYLOAD, KID, PRIVATE_KEY)

    with pytest.raises(ValueError):
        verify_sign1(
            message,
            {KID: PRIVATE_KEY.public_key()},
            ErrorCode.NBSR_E_INTERNAL,
        )
```

- [ ] **Step 2: Run the new tests and confirm RED**

Run:

```powershell
python -m pytest -q tests/protocol/test_cose.py -k "verify_sign1"
```

Expected: nonzero because `verify_sign1` is absent.

- [ ] **Step 3: Implement exact structural verification**

Add a fixed verification error and validate the structure before signature
verification:

```python
from collections.abc import Mapping

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from nbsr.protocol.cbor import decode_deterministic


_VERIFICATION_CODES = frozenset(
    {
        ErrorCode.NBSR_E_RECORD_UNTRUSTED,
        ErrorCode.NBSR_E_GRANT_INVALID,
    }
)


def _verification_error(code: ErrorCode) -> ProtocolViolation:
    return ProtocolViolation(code, "Invalid COSE Sign1")


def verify_sign1(
    message: bytes,
    keys: Mapping[bytes, Ed25519PublicKey],
    failure_code: ErrorCode,
) -> VerifiedSign1:
    if failure_code not in _VERIFICATION_CODES:
        raise ValueError("unsupported COSE verification failure code")
    if not isinstance(keys, Mapping):
        raise TypeError("keys must be a mapping")
    try:
        if type(message) is not bytes or not message.startswith(_TAG_18):
            raise _verification_error(failure_code)
        body = decode_deterministic(message[1:])
        if type(body) is not list or len(body) != 4:
            raise _verification_error(failure_code)
        protected, unprotected, payload, signature = body
        if (
            type(protected) is not bytes
            or unprotected != {}
            or type(payload) is not bytes
            or type(signature) is not bytes
            or len(signature) != 64
        ):
            raise _verification_error(failure_code)
        protected_map = decode_deterministic(protected)
        if (
            type(protected_map) is not dict
            or set(protected_map) != {1, 4}
            or type(protected_map[1]) is not int
            or protected_map[1] != _ALGORITHM_EDDSA
        ):
            raise _verification_error(failure_code)
        kid = _require_kid_value(protected_map[4])
        key = keys.get(kid)
        if not isinstance(key, Ed25519PublicKey):
            raise _verification_error(failure_code)
        to_be_signed = encode_deterministic(
            ["Signature1", protected, b"", payload]
        )
        key.verify(signature, to_be_signed)
        return VerifiedSign1(payload=payload, kid=kid)
    except ProtocolViolation as exc:
        if exc.code is ErrorCode.NBSR_E_OVER_CAPACITY:
            raise
        if exc.code is failure_code:
            raise
        raise _verification_error(failure_code) from exc
    except (InvalidSignature, KeyError, TypeError, ValueError) as exc:
        raise _verification_error(failure_code) from exc
```

- [ ] **Step 4: Run the verification tests and confirm GREEN**

Run:

```powershell
python -m pytest -q tests/protocol/test_cose.py -k "verify_sign1"
```

Expected: every selected verification test passes.

- [ ] **Step 5: Commit Task 2**

```powershell
git add nbsr/protocol/cose.py tests/protocol/test_cose.py
git commit -m "feat(protocol): verify constrained Ed25519 COSE Sign1"
```

---

### Task 3: Freeze negative profile and algorithm-confusion behavior

**Files:**
- Modify: `tests/protocol/test_cose.py`
- Modify: `nbsr/protocol/cose.py`

**Interfaces:**
- Consumes: Task 2 verifier.
- Produces: complete bounded rejection behavior with no new public API.

- [ ] **Step 1: Add a test-only raw Sign1 constructor**

Add:

```python
def raw_sign1(
    protected_map: object,
    *,
    unprotected: object = None,
    payload: object = PAYLOAD,
    signature: object = b"\x00" * 64,
    tag: bytes = b"\xd2",
) -> bytes:
    protected = encode_deterministic(protected_map)
    body = [
        protected,
        {} if unprotected is None else unprotected,
        payload,
        signature,
    ]
    return tag + encode_deterministic(body)
```

- [ ] **Step 2: Add table-driven header and structure rejection tests**

Cover these exact cases:

```python
@pytest.mark.parametrize(
    "message",
    (
        raw_sign1({4: KID}),
        raw_sign1({1: -7, 4: KID}),
        raw_sign1({1: -8, 4: KID, 2: [1]}),
        raw_sign1({4: KID}, unprotected={1: -8}),
        raw_sign1({1: -8, 4: KID}, unprotected={4: KID}),
        raw_sign1({1: -8, 4: b""}),
        raw_sign1({1: -8, 4: b"k" * 65}),
        raw_sign1({1: -8, 4: "text-kid"}),
        raw_sign1({1: -8, 4: KID}, payload=None),
        raw_sign1({1: -8, 4: KID}, tag=b"\xd1"),
        raw_sign1({1: -8, 4: KID}) + b"\x00",
    ),
)
def test_rejects_non_profile_headers_and_structures(message: bytes) -> None:
    with pytest.raises(ProtocolViolation) as rejected:
        verify_sign1(
            message,
            {KID: PRIVATE_KEY.public_key()},
            ErrorCode.NBSR_E_RECORD_UNTRUSTED,
        )

    assert rejected.value.code is ErrorCode.NBSR_E_RECORD_UNTRUSTED
```

Extend the parameter table with:

```python
raw_sign1({1: True, 4: KID})
raw_sign1({1: -8, 4: 7})
raw_sign1({1: -8, 4: KID}, signature=b"")
raw_sign1({1: -8, 4: KID}, signature=b"\x00" * 63)
raw_sign1({1: -8, 4: KID}, signature=b"\x00" * 65)
b"\xd2" + encode_deterministic([])
b"\xd2" + encode_deterministic(
    [encode_deterministic({1: -8, 4: KID}), {}, PAYLOAD]
)
```

Pass `{KID: object()}` as the trust context in a separate test and require the
selected failure code, proving that a non-Ed25519 public key is rejected.

- [ ] **Step 3: Add tamper and resource-limit tests**

Build a valid message, then independently rebuild it with:

- a changed protected `kid` and the original signature;
- a changed payload and the original signature; and
- one flipped signature byte.

Each must produce the selected failure code. Also create a tag-18 message
larger than `DEFAULT_LIMITS.max_total_bytes`; it must preserve
`NBSR_E_OVER_CAPACITY`.

- [ ] **Step 4: Run all focused tests and implement only missing mappings**

Run:

```powershell
python -m pytest -q tests/protocol/test_cose.py
```

Expected before any needed fix: at least one new negative test fails.

Adjust only the structural conditions or bounded exception list needed for the
failing case. Do not accept another algorithm, tag, header, key type, payload
form, or error code.

- [ ] **Step 5: Re-run and confirm GREEN**

Run:

```powershell
python -m pytest -q tests/protocol/test_cose.py
python -m ruff check nbsr/protocol/cose.py tests/protocol/test_cose.py
python -m ruff format --check nbsr/protocol/cose.py tests/protocol/test_cose.py
```

Expected: all commands exit 0.

- [ ] **Step 6: Commit Task 3**

```powershell
git add nbsr/protocol/cose.py tests/protocol/test_cose.py
git commit -m "test(protocol): reject non-profile COSE Sign1 inputs"
```

---

### Task 4: Enforce D6-A3 `kid` bindings and repository isolation

**Files:**
- Modify: `tests/protocol/test_cose.py`
- Modify: `nbsr/protocol/cose.py`

**Interfaces:**
- Consumes: Task 2 `VerifiedSign1`.
- Produces:
  - `require_kid(verified, expected_kid, failure_code) -> None`

- [ ] **Step 1: Write failing `kid` binding tests**

Use `encode_model`, `decode_service_record`, `decode_revocation`, and
`decode_route_grant` with the existing valid model constructors. Assert:

```python
verified = verify_sign1(
    sign1(encode_model(record), record.owner_key_id, PRIVATE_KEY),
    {record.owner_key_id: PRIVATE_KEY.public_key()},
    ErrorCode.NBSR_E_RECORD_UNTRUSTED,
)
decoded = decode_service_record(verified.payload)
require_kid(
    verified,
    decoded.owner_key_id,
    ErrorCode.NBSR_E_RECORD_UNTRUSTED,
)
```

Repeat for Revocation with `issuer_key_id`. A different expected `kid` must
raise the selected error. For RouteGrant, show that verification succeeds only
when the supplied authorized issuer mapping contains the protected `kid`.

Assert that `nbsr.protocol.cose` exports no RouteIntent, ProtocolError, or
ControlEnvelope signing wrapper.

- [ ] **Step 2: Run D6-A3 tests and confirm RED**

Run:

```powershell
python -m pytest -q tests/protocol/test_cose.py -k "kid_binding or authorized_issuer or unsigned"
```

Expected: nonzero because `require_kid` is absent.

- [ ] **Step 3: Implement the minimum binding helper**

Add:

```python
def require_kid(
    verified: VerifiedSign1,
    expected_kid: bytes,
    failure_code: ErrorCode,
) -> None:
    if failure_code not in _VERIFICATION_CODES:
        raise ValueError("unsupported COSE verification failure code")
    if (
        not isinstance(verified, VerifiedSign1)
        or type(expected_kid) is not bytes
        or verified.kid != expected_kid
    ):
        raise _verification_error(failure_code)
```

- [ ] **Step 4: Run focused and protocol suites**

Run:

```powershell
python -m pytest -q tests/protocol/test_cose.py
python -m pytest -q tests/protocol
```

Expected: all COSE and existing protocol tests pass.

- [ ] **Step 5: Run complete validation**

Run:

```powershell
python -m pytest -q -p no:cacheprovider --basetemp=C:\Users\bajra\.codex\visualizations\2026\07\26\019f9f86-8b83-7cd3-92bb-c334bd9f6f8b\pytest-wp1-task5-full
python -m ruff check nbsr tests scripts
python -m ruff format --check nbsr tests scripts
python -m pip check
python scripts/generate_core_v02_vectors.py --check vectors/core-v0.2
git diff --check
```

Expected: every command exits 0; no test is removed or skipped to obtain
green.

- [ ] **Step 6: Verify scope**

Run:

```powershell
git status --short
git diff --name-only
git diff -- nbsr/name_relay.py nbsr/legacy_origin.py crates/nbsr-transport
```

Expected: only `nbsr/protocol/cose.py` and
`tests/protocol/test_cose.py` are task changes; the runtime and Rust transport
diff is empty.

- [ ] **Step 7: Commit Task 4**

```powershell
git add nbsr/protocol/cose.py tests/protocol/test_cose.py
git commit -m "feat(protocol): enforce Core v0.1 COSE kid bindings"
```

## Final acceptance gate

Task 5 is complete only if:

- signing is deterministic and emits exact preferred tag 18;
- verification accepts only protected `{1: -8, 4: kid}`;
- external AAD is fixed to empty and payloads are attached;
- only Ed25519 keys are accepted;
- trust lookup is caller-scoped;
- record/revocation `kid` bindings and RouteGrant issuer context are proven;
- every malformed, confused, untrusted, or tampered case fails closed;
- CBOR capacity failures remain `NBSR_E_OVER_CAPACITY`;
- full protocol and repository validation pass; and
- no runtime, vector, registry, schema, state, transition, extension, or
  wrapper-set change occurs.
