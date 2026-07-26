# NBSR WP1 Protocol Data Model Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` (recommended) or
> `superpowers:executing-plans` to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Freeze Protocol Core v0.1 byte structures, Ed25519 COSE Sign1
behavior, state types, and deterministic valid/invalid vectors without changing
the current network services.

**Architecture:** Add a dependency-light `nbsr.protocol` package that has no
imports from FastAPI, OPA, Envoy, Kubernetes, cloud SDKs, operating-system
adapters, or current JSON/JWT service code. A strict structural validator gates
all CBOR before semantic schema parsing. Signed objects use a deliberately
narrow COSE Sign1 Ed25519 profile backed by `cryptography`; the current
enterprise and ISP prototype paths remain untouched.

**Tech Stack:** Python `>=3.12,<3.14`, `cbor2`, `cryptography`, `dataclasses`,
`enum`, `pytest`, `hypothesis`, Ruff.

## Global Constraints

- Read
  `docs/architecture/NBSR_Protocol_Vision_V3_and_Codex_Build_Directive.md`,
  `docs/protocol/wp1-decisions.md`, `docs/protocol/status.md`,
  `docs/vision-v2-conformance.md`, `docs/security-hardening-report.md`,
  `docs/threat-model.md`, and the current name-routing tests before editing.
- Obtain explicit approval of D1-D5 in `docs/protocol/wp1-decisions.md` before
  changing production code or dependencies.
- Work only on WP1. Do not begin the Name Node, QUIC transport, origin
  connector, federation, or gateway packaging.
- Use RFC 8949 Core Deterministic Encoding for all signed payloads and native
  messages, including bytewise lexicographic ordering of deterministic encoded
  map keys.
- The NBSR re-encoder owns deterministic encoding and acceptance checks; do
  not use `cbor2.dumps(..., canonical=True)`.
- Use COSE Sign1 with tag 18, protected `alg=-8`, protected opaque byte-string
  `kid` of 1-64 bytes scoped to the caller trust context, empty external AAD,
  attached payload, and Ed25519 keys only.
- Use proof-of-possession data structures; do not add bearer authorization to
  the ISP/core profile.
- Keep protocol code independent of current APIs and deployment adapters.
- Keep all tests deterministic and offline.
- Never place origin addresses, production secrets, raw subscriber identities,
  or reusable grants in fixtures, valid vectors, errors, or logs. RFC 5737 and
  RFC 3849 documentation literals are permitted only in invalid rejection
  vectors that prove IP-shaped origin data fails closed.
- Fail closed on duplicate keys, non-deterministic encodings, unknown Core
  fields, unknown critical extensions, unsupported algorithms, signature
  errors, stale sequence, rollback, invalid time windows, and resource bounds.
- Preserve every current test and demo.
- Do not claim Core v0.1 conformance or production readiness after WP1.

---

## File structure to create or modify

| Path | Responsibility |
|---|---|
| `pyproject.toml` | Add bounded CBOR and property-test dependencies |
| `constraints/runtime.txt` | Pin the resolved CBOR runtime version |
| `constraints/dev.txt` | Pin the resolved CBOR and Hypothesis development versions |
| `nbsr/protocol/__init__.py` | Export the stable WP1 public API only |
| `nbsr/protocol/errors.py` | Typed, stable, non-sensitive protocol exceptions |
| `nbsr/protocol/registry.py` | Protocol, message, error, and field registries |
| `nbsr/protocol/states.py` | Resolution, tunnel, stream, and connector state types and legal transitions |
| `nbsr/protocol/cbor.py` | Bounded structural scan plus deterministic CBOR encode/decode |
| `nbsr/protocol/fields.py` | Reusable field validators and canonical identifier/name helpers |
| `nbsr/protocol/models.py` | Immutable ServiceRecord, RouteIntent, RouteGrant, Revocation, Error, and envelope models |
| `nbsr/protocol/schemas.py` | Numeric-key wire mappings and strict semantic decoding |
| `nbsr/protocol/cose.py` | Narrow COSE Sign1 Ed25519 sign/verify helper |
| `tests/protocol/test_registry.py` | Frozen numeric registries |
| `tests/protocol/test_states.py` | State transition behavior |
| `tests/protocol/test_cbor.py` | Deterministic and rejection tests |
| `tests/protocol/test_models.py` | Field, privacy, sequence, and time invariants |
| `tests/protocol/test_schemas.py` | Model-to-wire round trips and critical-field behavior |
| `tests/protocol/test_cose.py` | COSE profile, tamper, and algorithm-confusion tests |
| `tests/protocol/test_vectors.py` | Checked-in golden vector verification |
| `tests/protocol/test_properties.py` | Bounded Hypothesis properties |
| `tests/vectors/core-v0.1/manifest.json` | Human-readable vector index and expected results |
| `tests/vectors/core-v0.1/*.cbor` | Exact valid and invalid wire bytes |
| `tests/vectors/core-v0.1/test-ed25519-public.hex` | Public test key |
| `tools/generate_core_v01_vectors.py` | Deterministic vector generator using labeled test-only key material |
| `docs/protocol/core-v0.1-wire.md` | Frozen WP1 wire contract and numeric tables |
| `docs/protocol/status.md` | Evidence update after all WP1 checks pass |

The existing `nbsr/name_security.py` JWT binding, `nbsr/name_control.py` JSON
API, relay framing, and enterprise ticket code are not migrated in WP1.

---

### Task 1: Approve the wire-profile decision and lock dependencies

**Files:**
- Review: `docs/protocol/wp1-decisions.md`
- Modify: `pyproject.toml`
- Modify: `constraints/runtime.txt`
- Modify: `constraints/dev.txt`
- Test: `tests/protocol/test_dependencies.py`

**Interfaces:**
- Consumes: approved D1-D5 decision record.
- Produces: `cbor2` runtime dependency and `hypothesis` development dependency.

- [ ] **Step 1: Record explicit approval**

Add this line below the title in `docs/protocol/wp1-decisions.md`:

```markdown
**Decision:** approved for WP1 implementation on 2026-07-26 by Petrit Bahtiri
with amendments A1-A4 recorded in `docs/protocol/wp1-decisions.md`.
```

Do not continue if the human requests a different CBOR/COSE strategy.

- [ ] **Step 2: Write the failing dependency-boundary test**

Create `tests/protocol/test_dependencies.py`:

```python
from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PROTOCOL = ROOT / "nbsr" / "protocol"
FORBIDDEN = {
    "fastapi",
    "jwt",
    "kubernetes",
    "opa",
    "pydantic",
    "uvicorn",
}


def test_protocol_core_has_no_adapter_dependencies() -> None:
    assert PROTOCOL.is_dir()
    violations: list[str] = []
    for path in sorted(PROTOCOL.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            for name in names:
                if name.split(".", 1)[0] in FORBIDDEN:
                    violations.append(f"{path.name}: {name}")
    assert violations == []
```

- [ ] **Step 3: Run the test and verify the protocol package is absent**

Run:

```bash
python -m pytest tests/protocol/test_dependencies.py -q
```

Expected: fail at `assert PROTOCOL.is_dir()` because `nbsr/protocol` has not
been created.

- [ ] **Step 4: Add bounded dependencies**

Update `pyproject.toml`:

```toml
dependencies = [
  "cbor2>=5.7,<6",
  "cryptography>=44,<46",
  "dnslib>=0.9.26,<0.10",
  "fastapi>=0.115,<0.117",
  "httpx>=0.28,<0.29",
  "pydantic-settings>=2.7,<3",
  "PyJWT>=2.10,<3",
  "uvicorn>=0.34,<0.36",
]

[project.optional-dependencies]
dev = [
  "hypothesis>=6.136,<7",
  "pytest>=8.3,<9",
  "pytest-asyncio>=1.4,<2",
  "ruff>=0.9,<0.12",
]
```

Create `nbsr/protocol/__init__.py` with only a module docstring:

```python
"""Dependency-light Name-Based Secure Routing Protocol Core v0.1 types."""
```

- [ ] **Step 5: Resolve and record exact dependency constraints**

Install the bounded project dependencies, then update:

- `constraints/runtime.txt` with the resolved `cbor2==X.Y.Z`; and
- `constraints/dev.txt` with the same `cbor2==X.Y.Z` plus the resolved
  `hypothesis==X.Y.Z` and any new transitive dependency.

Regenerate or edit the constraint files using the repository's existing sorted
`package==version` format. Verify that installing with each constraint file
succeeds:

```bash
python -m pip install --constraint constraints/runtime.txt -e .
python -m pip install --constraint constraints/dev.txt -e ".[dev]"
```

- [ ] **Step 6: Install and run the boundary test**

Run:

```bash
python -m pip install -e ".[dev]"
python -m pytest tests/protocol/test_dependencies.py -q
```

Expected: one passed test.

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml constraints/runtime.txt constraints/dev.txt \
  nbsr/protocol/__init__.py \
  tests/protocol/test_dependencies.py docs/protocol/wp1-decisions.md
git commit -m "build(protocol): lock WP1 dependencies and boundary"
```

---

### Task 2: Freeze registries, error types, and state transitions

**Files:**
- Create: `nbsr/protocol/errors.py`
- Create: `nbsr/protocol/registry.py`
- Create: `nbsr/protocol/states.py`
- Create: `tests/protocol/test_registry.py`
- Create: `tests/protocol/test_states.py`

**Interfaces:**
- Produces: `ProtocolVersion`, `MessageType`, `ErrorCode`,
  `ResolutionState`, `TunnelState`, `StreamState`, `ConnectorState`,
  `ProtocolViolation`, `InvalidTransition`, and `transition(current, target)`.
- Consumed by: every later WP1 schema, COSE, and vector task.

- [ ] **Step 1: Write registry tests**

Create `tests/protocol/test_registry.py`:

```python
from nbsr.protocol.registry import ErrorCode, MessageType, ProtocolVersion


def test_core_version_is_frozen() -> None:
    assert int(ProtocolVersion.CORE_0_1) == 1


def test_message_codes_are_frozen() -> None:
    assert {item.name: int(item) for item in MessageType} == {
        "CLIENT_HELLO": 1,
        "EDGE_HELLO": 2,
        "ROUTE_OPEN": 3,
        "ROUTE_ACCEPT": 4,
        "ROUTE_REJECT": 5,
        "STREAM_OPEN": 6,
        "STREAM_ACCEPT": 7,
        "STREAM_REJECT": 8,
        "LEASE_RENEW": 9,
        "LEASE_RESULT": 10,
        "KEY_UPDATE_NOTICE": 11,
        "ROUTE_DRAIN": 12,
        "ROUTE_REVOKE": 13,
        "ROUTE_CLOSE": 14,
        "PING": 15,
        "PONG": 16,
        "ERROR": 17,
    }


def test_error_code_mapping_is_frozen() -> None:
    assert {item.name: int(item) for item in ErrorCode} == {
        "NBSR_E_NAME_INVALID": 1,
        "NBSR_E_NAME_NOT_FOUND": 2,
        "NBSR_E_RECORD_UNTRUSTED": 3,
        "NBSR_E_RECORD_STALE": 4,
        "NBSR_E_RECORD_REVOKED": 5,
        "NBSR_E_CONTEXT_REQUIRED": 6,
        "NBSR_E_HANDLE_EXHAUSTED": 7,
        "NBSR_E_ROUTE_DENIED": 8,
        "NBSR_E_GRANT_INVALID": 9,
        "NBSR_E_GRANT_EXPIRED": 10,
        "NBSR_E_PROOF_INVALID": 11,
        "NBSR_E_REPLAY": 12,
        "NBSR_E_PROFILE_UNSUPPORTED": 13,
        "NBSR_E_DOWNGRADE": 14,
        "NBSR_E_EDGE_UNAVAILABLE": 15,
        "NBSR_E_ORIGIN_UNAVAILABLE": 16,
        "NBSR_E_REVOKED": 17,
        "NBSR_E_OVER_CAPACITY": 18,
        "NBSR_E_INTERNAL": 19,
    }
```

- [ ] **Step 2: Write state-transition tests**

Create `tests/protocol/test_states.py`:

```python
import pytest

from nbsr.protocol.errors import InvalidTransition
from nbsr.protocol.states import TunnelState, transition


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (TunnelState.IDLE, TunnelState.DISCOVERING),
        (TunnelState.DISCOVERING, TunnelState.HANDSHAKING),
        (TunnelState.HANDSHAKING, TunnelState.AUTHENTICATING),
        (TunnelState.AUTHENTICATING, TunnelState.ACTIVE),
        (TunnelState.ACTIVE, TunnelState.RENEWING),
        (TunnelState.RENEWING, TunnelState.ACTIVE),
        (TunnelState.ACTIVE, TunnelState.DRAINING),
        (TunnelState.DRAINING, TunnelState.CLOSED),
        (TunnelState.ACTIVE, TunnelState.REVOKED),
    ],
)
def test_allowed_tunnel_transitions(current: TunnelState, target: TunnelState) -> None:
    assert transition(current, target) is target


def test_payload_state_cannot_skip_admission() -> None:
    with pytest.raises(InvalidTransition):
        transition(TunnelState.HANDSHAKING, TunnelState.ACTIVE)
```

- [ ] **Step 3: Run focused tests and confirm failure**

```bash
python -m pytest tests/protocol/test_registry.py tests/protocol/test_states.py -q
```

Expected: import errors for missing modules.

- [ ] **Step 4: Add exact registries and errors**

Implement `registry.py` using `enum.IntEnum`. Copy message codes exactly from
Vision V3. Assign error integers in section 25 order:

```python
class ProtocolVersion(IntEnum):
    CORE_0_1 = 1


class MessageType(IntEnum):
    CLIENT_HELLO = 1
    EDGE_HELLO = 2
    ROUTE_OPEN = 3
    ROUTE_ACCEPT = 4
    ROUTE_REJECT = 5
    STREAM_OPEN = 6
    STREAM_ACCEPT = 7
    STREAM_REJECT = 8
    LEASE_RENEW = 9
    LEASE_RESULT = 10
    KEY_UPDATE_NOTICE = 11
    ROUTE_DRAIN = 12
    ROUTE_REVOKE = 13
    ROUTE_CLOSE = 14
    PING = 15
    PONG = 16
    ERROR = 17
```

`errors.py` must expose stable codes without sensitive detail:

```python
class ProtocolViolation(ValueError):
    def __init__(self, code: ErrorCode, message: str = "Invalid NBSR protocol data") -> None:
        super().__init__(message)
        self.code = code


class InvalidTransition(ProtocolViolation):
    def __init__(self) -> None:
        super().__init__(ErrorCode.NBSR_E_INTERNAL, "Invalid NBSR state transition")
```

Use `NBSR_E_INTERNAL` only as a non-sensitive fallback when no specific
registry code describes the failure. Parser, validation, trust, capacity,
replay, expiry, policy, and cryptographic failures must use their applicable
specific codes.

- [ ] **Step 5: Add state enums and explicit transition tables**

Use `enum.StrEnum`. Do not infer legal movement from enum ordering. Define
separate immutable transition maps for resolution, tunnel, stream, and
connector states. `transition()` must reject cross-enum transitions and
unlisted targets.

- [ ] **Step 6: Run focused tests**

```bash
python -m pytest tests/protocol/test_registry.py tests/protocol/test_states.py -q
python -m ruff check nbsr/protocol tests/protocol
```

Expected: all focused tests pass and Ruff reports no errors.

- [ ] **Step 7: Commit**

```bash
git add nbsr/protocol/errors.py nbsr/protocol/registry.py \
  nbsr/protocol/states.py tests/protocol/test_registry.py \
  tests/protocol/test_states.py
git commit -m "feat(protocol): freeze Core v0.1 registries and states"
```

---

### Task 3: Build the bounded deterministic CBOR gate

**Files:**
- Create: `nbsr/protocol/cbor.py`
- Create: `tests/protocol/test_cbor.py`

**Interfaces:**
- Produces:
  `encode_deterministic(value: object) -> bytes`,
  `decode_deterministic(data: bytes, limits: CborLimits = DEFAULT_LIMITS) -> object`,
  and immutable `CborLimits`.
- Consumed by: schemas, COSE, and vectors.

- [ ] **Step 1: Write deterministic encoding tests**

```python
from nbsr.protocol.cbor import decode_deterministic, encode_deterministic


def test_map_encoding_is_stable() -> None:
    first = encode_deterministic({2: b"b", 1: b"a"})
    second = encode_deterministic({1: b"a", 2: b"b"})
    assert first == second == bytes.fromhex("a2014161024162")
    assert decode_deterministic(first) == {1: b"a", 2: b"b"}
```

- [ ] **Step 2: Write exact invalid-byte tests**

Add vectors that must fail before semantic decoding:

```python
import pytest

from nbsr.protocol.cbor import decode_deterministic
from nbsr.protocol.errors import ProtocolViolation


@pytest.mark.parametrize(
    "wire",
    [
        bytes.fromhex("1817"),          # 23 encoded non-preferentially
        bytes.fromhex("9f0102ff"),      # indefinite array
        bytes.fromhex("bf01020103ff"),  # indefinite map with duplicate key
        bytes.fromhex("a201020103"),    # duplicate key
        bytes.fromhex("a202000100"),    # map keys out of deterministic order
        bytes.fromhex("f93e00"),        # floating point
        bytes.fromhex("d81800"),        # tag outside the COSE entry point
    ],
)
def test_non_core_deterministic_forms_are_rejected(wire: bytes) -> None:
    with pytest.raises(ProtocolViolation):
        decode_deterministic(wire)
```

- [ ] **Step 3: Write resource-limit tests**

Test maximum total bytes, nesting depth, map pairs, array items, text bytes,
and byte-string bytes. Each over-limit input must raise
`NBSR_E_OVER_CAPACITY` without allocating the declared size.

- [ ] **Step 4: Run tests and confirm failure**

```bash
python -m pytest tests/protocol/test_cbor.py -q
```

Expected: missing module failure.

- [ ] **Step 5: Implement a structural scanner before `cbor2.loads`**

The scanner must walk the original bytes and return the final offset plus raw
key slices for maps. It must:

- reject additional-information value 31;
- enforce shortest integer/length forms;
- reject floats, unsupported simple values, and tags unless
  `allow_top_level_tag=18` was explicitly passed by the COSE entry point;
- bound depth and container sizes before descending;
- compare complete deterministic encoded key bytes in strictly increasing
  bytewise lexicographic order as required by RFC 8949 Core Deterministic
  Encoding;
- reject equal raw key encodings as duplicates;
- reject trailing bytes.

After scanning, decode primitives with `cbor2.loads`, re-encode with the NBSR
deterministic encoder implemented in this module, and require exact byte
equality. The NBSR encoder must directly emit preferred integer/length forms
and sort map entries by bytewise lexicographic comparison of the complete
deterministic encoded key bytes. It must not call
`cbor2.dumps(..., canonical=True)`. The COSE entry point compares tag-aware
NBSR re-encoding.

- [ ] **Step 6: Run focused tests and Ruff**

```bash
python -m pytest tests/protocol/test_cbor.py -q
python -m ruff check nbsr/protocol/cbor.py tests/protocol/test_cbor.py
```

Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add nbsr/protocol/cbor.py tests/protocol/test_cbor.py
git commit -m "feat(protocol): enforce deterministic bounded CBOR"
```

---

### Task 4: Define immutable models and numeric wire schemas

**Approval prerequisite:** D6 in `docs/protocol/wp1-decisions.md` must be
human-approved. `docs/protocol/core-v0.1-wire-schema.md` is the sole source for
all Task 4 numeric keys, required/optional fields, CBOR wire types, bounds, and
semantic validation. Do not begin this task while D6 is pending.

**Files:**
- Create: `nbsr/protocol/fields.py`
- Create: `nbsr/protocol/models.py`
- Create: `nbsr/protocol/schemas.py`
- Create: `tests/protocol/test_models.py`
- Create: `tests/protocol/test_schemas.py`

**Interfaces:**
- Produces immutable dataclasses:
  `ServiceRecord`, `RouteIntent`, `RouteGrant`, `Revocation`, `ProtocolError`,
  and `ControlEnvelope`.
- Produces:
  `encode_model(model) -> bytes`,
  `decode_service_record(bytes) -> ServiceRecord`,
  `decode_route_intent(bytes) -> RouteIntent`,
  `decode_route_grant(bytes) -> RouteGrant`,
  `decode_revocation(bytes) -> Revocation`,
  `decode_error(bytes) -> ProtocolError`,
  and `decode_envelope(bytes) -> ControlEnvelope`.

- [ ] **Step 1: Write canonical-field tests**

Test:

- `API.Example.COM.` normalizes only at presentation input and the signed model
  accepts only `api.example.com`;
- IP literals, Unicode, empty labels, 64-octet labels, and names over 253
  octets fail;
- identifiers reject uppercase, whitespace, path traversal, and control bytes;
- timestamps reject booleans, negatives, reversed windows, and excessive
  lifetime;
- IDs and nonces require exactly 16 bytes;
- digests require exactly 32 bytes.

- [ ] **Step 2: Write privacy and rollback tests**

```python
import pytest

from nbsr.protocol.errors import ProtocolViolation
from nbsr.protocol.schemas import decode_service_record


def test_service_record_rejects_origin_address_field() -> None:
    # Key 50 is inside the reserved Core range but is not defined.
    wire = encode_deterministic({0: 1, 1: "api.example.com", 50: "203.0.113.9"})
    with pytest.raises(ProtocolViolation):
        decode_service_record(wire)


def test_service_record_requires_monotonic_sequence() -> None:
    record = valid_service_record(sequence=41)
    with pytest.raises(ProtocolViolation):
        record.require_newer_than(42)
```

- [ ] **Step 3: Freeze envelope numeric keys**

Implement these already-frozen D6 Core keys:

| Key | Envelope field | Wire type |
|---:|---|---|
| 0 | protocol version | uint |
| 1 | message type | uint |
| 2 | request ID | 16-byte bstr |
| 3 | session ID | 16-byte bstr |
| 4 | monotonic sequence | uint |
| 5 | body | map |
| 6 | critical extension keys | array of uint |

Unknown keys `0..999` fail closed. Extension keys `>=1000` are permitted only
when the target schema permits extensions and the key is not listed in field
6. Duplicate critical-field entries fail.

- [ ] **Step 4: Freeze signed-object field maps**

Copy each numeric key and field constraint as an explicit literal from D6 in
`docs/protocol/core-v0.1-wire-schema.md`. Never infer a key from Vision V3
field order, table order, dataclass order, or declaration order. The six
implementation mappings must match the six approved D6 tables exactly.

RouteGrant uses the single `name_digest` form and `allowed_ports`.
ServiceRecord has no embedded signature. RouteIntent, Revocation, and
ProtocolError use their complete D6 schemas. No free-form remote error detail
is serialized in Core v0.1.

- [ ] **Step 5: Implement frozen dataclasses and semantic validators**

Use `@dataclass(frozen=True, slots=True)`. Convert list inputs to tuples during
construction. Reject duplicate ports, transports, profiles, edge IDs, and
critical keys. Permit only TCP in Core v0.1 models even though registries leave
room for later UDP profiles.

- [ ] **Step 6: Implement strict schema decode**

Decode through `decode_deterministic()` first. Validate exact types using
`type(value) is int` so booleans cannot pass as integers. Check unknown fields
before constructing dataclasses. Return a fresh immutable object and never
retain references to decoded mutable maps/lists.

- [ ] **Step 7: Run focused tests**

```bash
python -m pytest tests/protocol/test_models.py tests/protocol/test_schemas.py -q
python -m ruff check nbsr/protocol tests/protocol
```

Expected: all focused tests pass.

- [ ] **Step 8: Commit**

```bash
git add nbsr/protocol/fields.py nbsr/protocol/models.py \
  nbsr/protocol/schemas.py tests/protocol/test_models.py \
  tests/protocol/test_schemas.py
git commit -m "feat(protocol): add Core v0.1 models and wire schemas"
```

---

### Task 5: Implement the narrow COSE Sign1 Ed25519 profile

**Files:**
- Create: `nbsr/protocol/cose.py`
- Create: `tests/protocol/test_cose.py`

**Interfaces:**
- Produces:
  `sign1(payload: bytes, kid: bytes, key: Ed25519PrivateKey) -> bytes`
  and
  `verify_sign1(message: bytes, keys: Mapping[bytes, Ed25519PublicKey]) -> VerifiedSign1`.
- `VerifiedSign1` contains only `payload: bytes` and `kid: bytes`.

- [ ] **Step 1: Write valid sign/verify test**

Use `Ed25519PrivateKey.from_private_bytes(bytes(range(32)))` as clearly labeled
test-only material. Assert signing the same payload twice produces identical
COSE bytes and verification returns the original payload and `kid`.

- [ ] **Step 2: Write algorithm-confusion tests**

Reject all of the following:

- `alg` missing;
- `alg` in the unprotected map;
- `alg=-7` or any value other than `-8`;
- duplicate `alg` or `kid` across protected and unprotected maps;
- empty or oversized `kid`;
- non-Ed25519 key object;
- detached or null payload;
- non-empty external AAD;
- unknown protected critical header;
- absent tag 18 or a different tag;
- trailing bytes;
- tampered protected header, payload, or signature;
- `kid` encoded as text, integer, empty bytes, or more than 64 bytes;
- key lookup miss within the caller-supplied trust context.

- [ ] **Step 3: Run tests and confirm failure**

```bash
python -m pytest tests/protocol/test_cose.py -q
```

Expected: missing module failure.

- [ ] **Step 4: Implement the exact COSE structures**

Protected header:

```python
protected = encode_deterministic({1: -8, 4: kid})
```

Signature structure:

```python
sig_structure = encode_deterministic(
    ["Signature1", protected, b"", payload]
)
signature = key.sign(sig_structure)
```

COSE Sign1 body before tag:

```python
[protected, {}, payload, signature]
```

Encode with required CBOR tag 18. Verification must structurally validate the
tagged value, decode the protected bytes with the deterministic decoder,
enforce the exact protected/unprotected header profile, preserve `kid` as
opaque bytes, look it up only in the caller-supplied trust context, verify
Ed25519, and return immutable verified data. Convert every cryptographic or
format failure to stable `NBSR_E_GRANT_INVALID` or
`NBSR_E_RECORD_UNTRUSTED` according to the caller-selected object class; do not
return library exception text to peers.

- [ ] **Step 5: Run focused tests**

```bash
python -m pytest tests/protocol/test_cose.py -q
python -m ruff check nbsr/protocol/cose.py tests/protocol/test_cose.py
```

Expected: all focused tests pass.

- [ ] **Step 6: Commit**

```bash
git add nbsr/protocol/cose.py tests/protocol/test_cose.py
git commit -m "feat(protocol): add constrained Ed25519 COSE Sign1"
```

---

### Task 6: Generate and freeze valid and invalid Core v0.1 vectors

**Files:**
- Create: `tools/generate_core_v01_vectors.py`
- Create: `tests/vectors/core-v0.1/manifest.json`
- Create: `tests/vectors/core-v0.1/*.cbor`
- Create: `tests/vectors/core-v0.1/test-ed25519-public.hex`
- Create: `tests/protocol/test_vectors.py`

**Interfaces:**
- Produces cross-language byte fixtures and expected symbolic results.
- Consumed by all future NBSR implementations and conformance suites.

- [ ] **Step 1: Write the vector manifest test**

The test loads the manifest, verifies SHA-256 for every file, routes each vector
to its declared decoder/verifier, and asserts either the expected model summary
or exact `ErrorCode.name`.

Manifest entries must have this shape:

```json
{
  "name": "route-grant-valid-01",
  "file": "route-grant-valid-01.cbor",
  "kind": "signed_route_grant",
  "valid": true,
  "sha256": "<64 lowercase hex characters>",
  "expected": {
    "route_id": "000102030405060708090a0b0c0d0e0f",
    "record_sequence": 42
  }
}
```

- [ ] **Step 2: Define the minimum vector catalog**

Valid:

- control envelope;
- ServiceRecord;
- RouteIntent;
- signed Route Grant;
- signed immediate revocation;
- ProtocolError.

Invalid:

- non-shortest integer;
- indefinite map;
- duplicate map key;
- unsorted map key;
- excessive nesting;
- wrong field type;
- unknown reserved Core field;
- unknown critical extension;
- duplicate critical extension;
- stale ServiceRecord sequence;
- expired/not-yet-valid record;
- reversed grant window;
- wrong grant name/service/transport/port/edge binding fixture;
- missing COSE algorithm;
- non-EdDSA algorithm;
- algorithm in unprotected header;
- wrong `kid`;
- tampered payload;
- tampered signature;
- origin-address-shaped unknown fields using `192.0.2.9`, `198.51.100.9`,
  `203.0.113.9`, and `2001:db8::9` only in invalid rejection vectors.

- [ ] **Step 3: Implement deterministic generation**

The generator must:

- refuse to run if output is outside `tests/vectors/core-v0.1`;
- use fixed Unix timestamps and fixed byte IDs;
- use only reserved `.example` names;
- use RFC 5737 IPv4 or RFC 3849 IPv6 literals only when generating explicitly
  invalid origin-address rejection vectors;
- use a fixed test-only 32-byte Ed25519 seed;
- write files atomically;
- sort manifest entries by name;
- include SHA-256 for every binary;
- never import service/API modules.

- [ ] **Step 4: Generate twice and prove stability**

```bash
python tools/generate_core_v01_vectors.py
sha256sum tests/vectors/core-v0.1/* > /tmp/nbsr-vectors-first.sha256
python tools/generate_core_v01_vectors.py
sha256sum tests/vectors/core-v0.1/* > /tmp/nbsr-vectors-second.sha256
diff -u /tmp/nbsr-vectors-first.sha256 /tmp/nbsr-vectors-second.sha256
```

Expected: `diff` has no output and exits zero.

- [ ] **Step 5: Run vector tests**

```bash
python -m pytest tests/protocol/test_vectors.py -q
```

Expected: every valid and invalid vector produces the declared result.

- [ ] **Step 6: Commit**

```bash
git add tools/generate_core_v01_vectors.py tests/vectors/core-v0.1 \
  tests/protocol/test_vectors.py
git commit -m "test(protocol): freeze Core v0.1 golden vectors"
```

---

### Task 7: Add bounded property tests and malformed-input coverage

**Files:**
- Create: `tests/protocol/test_properties.py`
- Modify: `tests/protocol/test_cbor.py`
- Modify: `tests/protocol/test_schemas.py`
- Modify: `tests/protocol/test_cose.py`

**Interfaces:**
- Consumes all WP1 public interfaces.
- Produces repeatable property coverage with saved regression examples only
  when an actual failure is found.

- [ ] **Step 1: Write deterministic round-trip properties**

Generate valid bounded models, encode, decode, and require:

```python
decoded == original
encode_model(decoded) == wire
```

Use fixed Hypothesis settings in CI:

```python
@settings(
    max_examples=300,
    deadline=None,
    derandomize=True,
    suppress_health_check=[HealthCheck.too_slow],
)
```

- [ ] **Step 2: Write arbitrary-byte rejection property**

For byte strings up to the configured maximum, decoding must either return a
bounded allowed CBOR value or raise `ProtocolViolation`. It must not raise
`RecursionError`, `MemoryError`, `UnicodeDecodeError`, `KeyError`, or raw
`cbor2` exceptions.

- [ ] **Step 3: Write mutation properties**

For each valid signed object:

- flip one byte in protected headers, payload, or signature;
- replace `alg=-8`;
- insert an unknown critical key;
- duplicate a map key at raw-wire level;
- increase a declared length beyond available bytes.

Every mutation must fail with a stable protocol error before any object is
trusted.

- [ ] **Step 4: Run property tests**

```bash
python -m pytest tests/protocol/test_properties.py -q
```

Expected: all properties pass deterministically.

- [ ] **Step 5: Run the complete WP1 suite**

```bash
python -m pytest tests/protocol -q
python -m ruff check nbsr/protocol tests/protocol tools/generate_core_v01_vectors.py
```

Expected: all WP1 tests and Ruff checks pass.

- [ ] **Step 6: Commit**

```bash
git add tests/protocol
git commit -m "test(protocol): harden Core v0.1 parsers with properties"
```

---

### Task 8: Publish the wire contract and verify zero regression

**Files:**
- Create: `docs/protocol/core-v0.1-wire.md`
- Modify: `docs/protocol/status.md`
- Modify: `nbsr/protocol/__init__.py`
- Test: `tests/test_documentation.py`

**Interfaces:**
- Produces the reviewed public WP1 API and the exact cross-language wire
  reference.
- Does not connect the new core to the current network services.

- [ ] **Step 1: Write the wire document**

Include:

- normative scope and non-claims;
- RFC 8949 deterministic restrictions;
- maximum sizes and nesting limits;
- every numeric message, error, envelope, and object field table;
- exact identifier, time, canonical-name, and digest formats;
- COSE Sign1 protected-header and signature-structure rules;
- extension and critical-field behavior;
- vector manifest location and regeneration command;
- privacy rule prohibiting origin addresses;
- incompatibility/versioning rule for future changes.

- [ ] **Step 2: Export only stable names**

Update `nbsr/protocol/__init__.py` to export registries, immutable models,
encode/decode entry points, COSE helpers, and stable exceptions. Do not export
internal scanner functions or mutable schema tables.

- [ ] **Step 3: Update status with observed evidence**

Change only rows proven by tests from `Planned` to `Implemented`. Keep QUIC,
Name Node, federation, multi-operator admission, HA, and production claims as
planned. Include exact test counts and environment only after running them.

- [ ] **Step 4: Run all available verification**

```bash
python -m pytest -q
python -m ruff check .
opa test policy -v
docker compose config --quiet
```

Expected:

- every existing test plus WP0/WP1 tests passes;
- no test is removed or skipped to obtain green status;
- Ruff passes;
- all five OPA tests pass when OPA is installed;
- Compose configuration validates when Docker is installed.

If OPA or Docker is unavailable, record the exact skipped command and reason;
do not convert the absence into a pass.

- [ ] **Step 5: Re-run deterministic vector comparison**

```bash
sha256sum tests/vectors/core-v0.1/* > /tmp/nbsr-before.sha256
python tools/generate_core_v01_vectors.py
sha256sum tests/vectors/core-v0.1/* > /tmp/nbsr-after.sha256
diff -u /tmp/nbsr-before.sha256 /tmp/nbsr-after.sha256
```

Expected: no differences.

- [ ] **Step 6: Scan for origin-address and secret leakage**

```bash
rg -n \
  'origin_(ip|address)|203\.0\.113\.|198\.51\.100\.|192\.0\.2\.|2001:db8:|PRIVATE KEY|Bearer ' \
  nbsr/protocol docs/protocol/core-v0.1-wire.md
python -m pytest tests/protocol/test_vectors.py -q -k documentation_ip
```

Expected: the source/document scan has no origin-address fields, bearer
grants, documentation IP literals, or production secrets. The focused vector
test passes only when RFC 5737/RFC 3849 literals occur in explicitly invalid
rejection vectors and each produces its declared rejection code. The
test-only key label may reference test material but must not use a PEM
`PRIVATE KEY` block in the vector directory.

- [ ] **Step 7: Commit**

```bash
git add nbsr/protocol/__init__.py docs/protocol/core-v0.1-wire.md \
  docs/protocol/status.md tests/test_documentation.py
git commit -m "docs(protocol): publish the WP1 wire contract"
```

---

## WP1 exit criteria

WP1 is complete only when all of the following are evidenced:

- D1-D5 have explicit human approval.
- Stable structures always encode to the same bytes.
- Non-deterministic, indefinite, duplicate-key, oversized, and unsupported CBOR
  forms fail before semantic trust.
- Unknown critical fields and unknown reserved Core fields fail closed.
- COSE Sign1 accepts only tagged, attached-payload, protected-header Ed25519.
- Algorithm confusion, header duplication, key mismatch, tampering, and
  signature failure are rejected.
- ServiceRecord rollback/staleness and invalid time windows are rejected.
- Every golden vector is reproducible and contains only public test material.
- Protocol core has no adapter/framework imports.
- All existing tests remain and the full available suite passes.
- Documentation still says that QUIC, the universal Name Node, HA, federation,
  and full Core v0.1 conformance are not implemented.
- Work stops before WP2.

## Self-review record

- **Spec coverage:** WP1 deliverables map to Tasks 2-7; dependency isolation,
  documentation, and full regression map to Tasks 1 and 8.
- **No-placeholder scan:** the plan contains explicit files, interfaces,
  commands, expected results, numeric registries, test cases, and commit
  boundaries.
- **Type consistency:** IDs are 16-byte `bytes`, COSE `kid` is an opaque
  1-64-byte `bytes` value scoped to caller trust context, digests are 32-byte
  `bytes`, times are integer Unix seconds, names are canonical ASCII strings,
  and all model collections are immutable tuples throughout the plan.
- **Scope boundary:** no task implements WP2 Name Node or WP3 QUIC behavior.
