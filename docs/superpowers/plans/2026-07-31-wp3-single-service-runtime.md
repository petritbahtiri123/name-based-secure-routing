# WP3 Single-Service Runtime Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prove, on loopback, that one mutually authenticated Core v0.2 QUIC
Transport Session can independently authorize one Route Context / Service
Channel and gate one TCP Application Stream without revealing or connecting to
an Origin Endpoint.

**Architecture:** Extend the isolated Rust `nbsr-transport` crate. Its
transport adapter remains the only Quinn owner; a versioned control codec,
bounded admission state, and application-stream gate remain separate Rust
modules. The existing Python Name Node, NameRelay, frozen Core v0.1 package,
and checked-in Core v0.2 fixture generator remain independent.

**Tech Stack:** Rust 1.97.1, Quinn 0.11.11, rustls 0.23.43, Tokio 1.53.1,
x509-parser 0.18.1, dcbor 0.25.2, coset 0.4.2, ed25519-dalek 2.2.0, and
sha2 0.11.0. Direct dependencies are exact-pinned and accepted only if all
checked-in Core v0.2 fixtures pass byte-for-byte.

## Global Constraints

- Work only on `codex/nbsr-v3-wp0-wp1`; do not merge `main` or push without
  explicit instruction.
- Preserve unrelated untracked paths `.codex-test-temp-w4/`, `.superpowers/`,
  and `docs/leakguard_phase19_qa_pack/`.
- Do not change D1-D6, 17 message codes, 19 error codes, Core v0.1 schemas,
  state registries, deterministic CBOR rules, COSE wrappers, or vectors.
- Core v0.2 accepts exactly version 2 after authenticated policy selection;
  Core v0.2 failure never causes automatic Core v0.1 fallback.
- Use loopback, ephemeral UDP ports, in-memory test CA material, deterministic
  fixture bytes, and bounded in-memory security state only.
- Source Edge is the QUIC client and Destination Edge is the QUIC server;
  TLS 1.3, mTLS, and ALPN `nbsr-quic-1` remain mandatory, and 0-RTT remains
  disabled.
- Admit at most one Service Channel and one Application Stream per lab
  Transport Session. WP4 owns multi-service session reuse and channel key
  derivation.
- No Origin Endpoint, origin name, connector, DNS answer, raw RouteGrant,
  private key, proof signature, or unbounded third-party exception reaches a
  public result, normal log, or test assertion.
- The accepted data path terminates in a bounded in-memory echo fixture. It
  must not open a TCP connection or forward to an origin.
- Every production change follows RED, GREEN, then focused verification before
  the listed commit. Stop for human review if any candidate dependency cannot
  satisfy every checked-in vector through public APIs.

## File map

| File | Responsibility |
|---|---|
| `crates/nbsr-transport/Cargo.toml` | Exact runtime dependency pins |
| `crates/nbsr-transport/Cargo.lock` | Resolved dependency freeze |
| `crates/nbsr-transport/src/core_v02.rs` | Bounded version-2 envelope/body and COSE validation |
| `crates/nbsr-transport/src/admission.rs` | Session replay state and single-channel RouteGrant admission |
| `crates/nbsr-transport/src/session.rs` | Version-locked control sequence over an authenticated transport |
| `crates/nbsr-transport/src/stream_gate.rs` | Post-admission QUIC stream gating and bounded echo |
| `crates/nbsr-transport/src/quinn_adapter.rs` | Sole Quinn endpoint, connection, and stream owner |
| `crates/nbsr-transport/tests/core_v02_vectors.rs` | Raw fixture and structural-rejection conformance |
| `crates/nbsr-transport/tests/admission.rs` | Route, proof, replay, expiry, and capacity behavior |
| `crates/nbsr-transport/tests/runtime.rs` | Real loopback control and application-stream lifecycle |
| `tests/test_wp3_single_service_runtime_documentation.py` | Repository isolation and non-claim anti-drift checks |

---

### Task 1: Establish Rust Core v0.2 fixture conformance

**Files:**
- Modify: `crates/nbsr-transport/Cargo.toml`
- Modify: `crates/nbsr-transport/Cargo.lock`
- Modify: `crates/nbsr-transport/src/lib.rs`
- Create: `crates/nbsr-transport/src/core_v02.rs`
- Create: `crates/nbsr-transport/tests/core_v02_vectors.rs`

**Interfaces:**
- Produces `CoreV02Limits { max_frame_bytes: 65_536 }`.
- Produces `CoreV02Message`, `CoreV02Reject`, and
  `decode_control_envelope(bytes: &[u8], limits: CoreV02Limits) -> Result<CoreV02Message, CoreV02Reject>`.
- Produces `validate_route_grant_sign1(bytes: &[u8], trusted_issuers: &IssuerTrust) -> Result<ValidatedRouteGrant, CoreV02Reject>`.

- [ ] **Step 1: Write failing raw-fixture tests**

Create tests loading these checked-in fixtures with `include_bytes!`:

```rust
#[test]
fn accepts_exact_client_hello_fixture() {
    let message = decode_control_envelope(
        include_bytes!("../../../vectors/core-v0.2/artifacts/valid/envelopes/client-hello.cbor"),
        CoreV02Limits::lab(),
    )
    .unwrap();
    assert_eq!(message.protocol_version(), 2);
    assert_eq!(message.message_type(), MessageType::ClientHello);
}

#[test]
fn rejects_nonpreferred_cbor_before_message_dispatch() {
    let error = decode_control_envelope(
        include_bytes!("../../../vectors/core-v0.2/artifacts/invalid/structural/cbor-nonpreferred-integer.bin"),
        CoreV02Limits::lab(),
    )
    .unwrap_err();
    assert_eq!(error, CoreV02Reject::ProfileUnsupported);
}
```

Add one table-driven test for every invalid structural fixture, both version
fixtures, the three valid HELLO/ROUTE/STREAM envelope fixtures, and the valid
RouteGrant Sign1 fixture. Require each successful decode to re-encode to the
identical input bytes.

- [ ] **Step 2: Run the fixture test and verify RED**

Run:

```powershell
& "$env:USERPROFILE\.cargo\bin\cargo.exe" test --manifest-path crates/nbsr-transport/Cargo.toml --test core_v02_vectors
```

Expected: nonzero because `core_v02` and its public API do not exist.

- [ ] **Step 3: Add exact-pinned codecs and implement the bounded decoder**

Add these direct dependencies:

```toml
dcbor = "=0.25.2"
coset = "=0.4.2"
ed25519-dalek = "=2.2.0"
sha2 = "=0.11.0"
```

Use `dcbor` first to require one complete deterministic item, shortest
encodings, bytewise map ordering, definite lengths, no duplicate keys, no
floats, no unsupported tags, and no trailing bytes. Decode only closed
numeric-key maps for the approved version-2 envelope and body tables. Use
`coset::CoseSign1` only after deterministic structural validation, require tag
18, protected `alg = -8`, protected opaque `kid`, attached payload, and no
unapproved header. Verify Ed25519 with `VerifyingKey::verify_strict` and use
`Sha256` for the exact RouteGrant digest.

- [ ] **Step 4: Run fixture tests and verify GREEN**

Run:

```powershell
& "$env:USERPROFILE\.cargo\bin\cargo.exe" test --locked --manifest-path crates/nbsr-transport/Cargo.toml --test core_v02_vectors
& "$env:USERPROFILE\.cargo\bin\cargo.exe" fmt --manifest-path crates/nbsr-transport/Cargo.toml -- --check
& "$env:USERPROFILE\.cargo\bin\cargo.exe" clippy --locked --manifest-path crates/nbsr-transport/Cargo.toml --all-targets -- -D warnings
```

Expected: all fixture outcomes match their manifest and every command exits 0.

- [ ] **Step 5: Commit Task 1**

```powershell
git add crates/nbsr-transport/Cargo.toml crates/nbsr-transport/Cargo.lock crates/nbsr-transport/src/lib.rs crates/nbsr-transport/src/core_v02.rs crates/nbsr-transport/tests/core_v02_vectors.rs
git commit -m "feat(wp3): validate Core v0.2 control fixtures in Rust"
```

### Task 2: Add bounded single-channel destination admission

**Files:**
- Modify: `crates/nbsr-transport/src/lib.rs`
- Create: `crates/nbsr-transport/src/admission.rs`
- Create: `crates/nbsr-transport/tests/admission.rs`

**Interfaces:**
- Consumes `CoreV02Message`, `ValidatedRouteGrant`, authenticated source and
  destination edge identities, and an injected `IssuerTrust`.
- Produces `DestinationAdmission::new(limits, policy, trust)`,
  `accept_client_hello`, `accept_route_open`, `active_channel`, and
  `AdmissionOutcome::{Accepted, Rejected(CoreV02Reject), Close}`.

- [ ] **Step 1: Write failing route-admission tests**

Create an in-memory `LabPolicy` that accepts only the service, destination
edge, TCP port, and policy digest encoded by the valid vectors. Test:

```rust
#[test]
fn route_open_creates_one_service_bound_channel_after_hello() {
    let mut admission = lab_admission();
    admission.accept_client_hello(valid_client_hello()).unwrap();
    admission.accept_edge_hello(valid_edge_hello()).unwrap();

    let accepted = admission.accept_route_open(valid_route_open()).unwrap();

    assert_eq!(accepted.channel_id(), [0x11; 16]);
    assert_eq!(accepted.route_id(), [0x22; 16]);
    assert_eq!(admission.active_channel().unwrap().service_id(), "svc_api");
}
```

Add focused tests for replayed session/request/nonce, bad RouteGrant signature,
expired grant, bad proof, wrong source edge, wrong destination edge, wrong
service, wrong TCP port, revoked grant, denied policy, and second channel
capacity. Each must leave `active_channel()` unchanged or absent.

- [ ] **Step 2: Run the admission test and verify RED**

Run:

```powershell
& "$env:USERPROFILE\.cargo\bin\cargo.exe" test --locked --manifest-path crates/nbsr-transport/Cargo.toml --test admission
```

Expected: nonzero because destination admission does not exist.

- [ ] **Step 3: Implement exact admission ordering**

`DestinationAdmission` stores one exact Core version, fixed-capacity replay
sets, one unused edge nonce, and at most one `ActiveChannel`. It performs, in
order: closed-map decode, session/request/sequence replay checks, COSE grant
verification in `IssuerTrust`, proof verification over the frozen transcript,
all grant/edge/service/transport/port/policy/expiry/revocation checks, then
capacity reservation. It returns the most specific frozen error and never
stores a rejected candidate.

- [ ] **Step 4: Run focused tests and verify GREEN**

Run:

```powershell
& "$env:USERPROFILE\.cargo\bin\cargo.exe" test --locked --manifest-path crates/nbsr-transport/Cargo.toml --test admission
& "$env:USERPROFILE\.cargo\bin\cargo.exe" clippy --locked --manifest-path crates/nbsr-transport/Cargo.toml --all-targets -- -D warnings
```

Expected: all admission tests pass without an origin object or connection.

- [ ] **Step 5: Commit Task 2**

```powershell
git add crates/nbsr-transport/src/lib.rs crates/nbsr-transport/src/admission.rs crates/nbsr-transport/tests/admission.rs
git commit -m "feat(wp3): admit one service-bound route channel"
```

### Task 3: Add a version-locked QUIC control session

**Files:**
- Modify: `crates/nbsr-transport/src/quinn_adapter.rs`
- Create: `crates/nbsr-transport/src/session.rs`
- Modify: `crates/nbsr-transport/src/lib.rs`
- Create: `crates/nbsr-transport/tests/runtime.rs`

**Interfaces:**
- Consumes `AuthenticatedConnection` and `DestinationAdmission`.
- Produces `ControlSession::open_source`, `ControlSession::accept_destination`,
  `send_frame`, `receive_frame`, and `close`.

- [ ] **Step 1: Write failing control-stream tests**

Use the existing loopback test CA and real Quinn connections. The Source opens
the first bidirectional stream and sends the valid CLIENT_HELLO fixture; the
Destination responds with EDGE_HELLO, then accepts ROUTE_OPEN. Assert stream 0
is the sole control stream, the messages are version 2, and a version-one
fixture produces `NBSR_E_DOWNGRADE` without a second connection attempt.

- [ ] **Step 2: Run the control-session test and verify RED**

Run:

```powershell
& "$env:USERPROFILE\.cargo\bin\cargo.exe" test --locked --manifest-path crates/nbsr-transport/Cargo.toml --test runtime control_session
```

Expected: nonzero because `AuthenticatedConnection` exposes no stream API and
`ControlSession` does not exist.

- [ ] **Step 3: Implement framed control I/O**

Keep all Quinn `open_bi`, `accept_bi`, `SendStream`, and `RecvStream` use in
`quinn_adapter.rs`. Encode each frame as a shortest-form QUIC variable-length
length plus the exact deterministic envelope bytes; reject zero, oversized,
non-shortest, truncated, and trailing frames. `session.rs` permits the exact
CLIENT_HELLO → EDGE_HELLO → ROUTE_OPEN → ROUTE_ACCEPT/ROUTE_REJECT sequence
and closes on any version mismatch or structurally uncorrelatable input.

- [ ] **Step 4: Run control tests and verify GREEN**

Run:

```powershell
& "$env:USERPROFILE\.cargo\bin\cargo.exe" test --locked --manifest-path crates/nbsr-transport/Cargo.toml --test runtime control_session
& "$env:USERPROFILE\.cargo\bin\cargo.exe" fmt --manifest-path crates/nbsr-transport/Cargo.toml -- --check
```

Expected: valid control flow passes; mismatch and malformed input fail closed.

- [ ] **Step 5: Commit Task 3**

```powershell
git add crates/nbsr-transport/src/lib.rs crates/nbsr-transport/src/quinn_adapter.rs crates/nbsr-transport/src/session.rs crates/nbsr-transport/tests/runtime.rs
git commit -m "feat(wp3): run version-locked QUIC route admission"
```

### Task 4: Gate one accepted application stream

**Files:**
- Modify: `crates/nbsr-transport/src/quinn_adapter.rs`
- Create: `crates/nbsr-transport/src/stream_gate.rs`
- Modify: `crates/nbsr-transport/src/lib.rs`
- Modify: `crates/nbsr-transport/tests/runtime.rs`

**Interfaces:**
- Consumes an accepted `ControlSession` and its single `ActiveChannel`.
- Produces `StreamGate::open`, `StreamGate::accept`, and
  `StreamGate::echo_once` with a fixed 4 KiB payload bound.

- [ ] **Step 1: Write failing application-stream tests**

Write a real loopback test that opens source stream ID 4, attempts a payload
before STREAM_ACCEPT, and asserts that the Destination resets it without
delivering a byte. Then complete the valid STREAM_OPEN/STREAM_ACCEPT exchange,
send `b"nbsr-lab"`, and assert the bounded in-memory echo returns exactly that
value. Assert no test value contains an origin hostname or IP address.

- [ ] **Step 2: Run the stream test and verify RED**

Run:

```powershell
& "$env:USERPROFILE\.cargo\bin\cargo.exe" test --locked --manifest-path crates/nbsr-transport/Cargo.toml --test runtime application_stream
```

Expected: nonzero because no stream gate or application stream API exists.

- [ ] **Step 3: Implement stream authorization and bounded echo**

Require a source-initiated bidirectional ID greater than zero and divisible by
four. Verify STREAM_OPEN against the active channel's exact channel ID, route
ID, RouteGrant digest, TCP transport, and port before emitting STREAM_ACCEPT.
Reserve the one stream only after checks pass. On rejection, use the approved
STREAM_REJECT when safely correlatable, otherwise close/reset; do not accept
or buffer application bytes. After acceptance, copy at most 4 KiB to the
in-memory echo and reset on excess.

- [ ] **Step 4: Run stream tests and verify GREEN**

Run:

```powershell
& "$env:USERPROFILE\.cargo\bin\cargo.exe" test --locked --manifest-path crates/nbsr-transport/Cargo.toml --test runtime application_stream
& "$env:USERPROFILE\.cargo\bin\cargo.exe" clippy --locked --manifest-path crates/nbsr-transport/Cargo.toml --all-targets -- -D warnings
```

Expected: no byte crosses the gate early; the accepted bounded echo succeeds;
no origin connection exists.

- [ ] **Step 5: Commit Task 4**

```powershell
git add crates/nbsr-transport/src/lib.rs crates/nbsr-transport/src/quinn_adapter.rs crates/nbsr-transport/src/stream_gate.rs crates/nbsr-transport/tests/runtime.rs
git commit -m "feat(wp3): gate one authorized application stream"
```

### Task 5: Freeze evidence and preserve repository boundaries

**Files:**
- Create: `tests/test_wp3_single_service_runtime_documentation.py`
- Modify: `docs/protocol/status.md`
- Modify: `docs/superpowers/plans/2026-07-28-v3.6-protocol-roadmap.md`
- Modify: `docs/protocol/wp3-single-service-transport-decision.md`

**Interfaces:**
- Consumes final runtime test evidence.
- Produces documentation that marks only the loopback single-service lab
  boundary as implemented and preserves every excluded capability as gated.

- [ ] **Step 1: Write failing anti-drift tests**

Require documentation to contain all of these exact statements:

```python
required = (
    "one Service Channel and one TCP Application Stream",
    "Origin Endpoint remains internal and is not connected",
    "Core v0.2 failure never retries as Core v0.1",
    "multi-service Transport Session reuse remains WP4",
    "NameRelay remains unchanged",
    "no production readiness claim",
)
```

Also assert no change appears under `nbsr/`, no Core v0.1 registry/schema test
expectation changes, and no new numeric message/error/state/extension/COSE
wrapper appears.

- [ ] **Step 2: Run the anti-drift test and verify RED**

Run:

```powershell
python -m pytest tests/test_wp3_single_service_runtime_documentation.py -q
```

Expected: nonzero because completion evidence is not documented.

- [ ] **Step 3: Record only proven outcomes**

Document exact loopback test counts, dependency versions, fixture count,
single-channel/one-stream limits, in-memory echo bound, origin-free boundary,
and every remaining WP4-WP8 gate. Do not claim origin forwarding, agent
installation, direct client capture, multi-service reuse, production trust,
HA, migration, resumption, handover, DNS recursion, or federation.

- [ ] **Step 4: Run complete validation**

Run:

```powershell
& "$env:USERPROFILE\.cargo\bin\cargo.exe" test --locked --manifest-path crates/nbsr-transport/Cargo.toml
& "$env:USERPROFILE\.cargo\bin\cargo.exe" fmt --manifest-path crates/nbsr-transport/Cargo.toml -- --check
& "$env:USERPROFILE\.cargo\bin\cargo.exe" clippy --locked --manifest-path crates/nbsr-transport/Cargo.toml --all-targets -- -D warnings
python -m pytest tests/test_wp3_single_service_runtime_documentation.py tests/test_wp3_rust_transport_isolation.py tests/protocol/test_registry.py tests/protocol/test_schemas.py tests/protocol/test_states.py tests/protocol/test_vectors.py -q
python -m pytest -q --basetemp=.wp3-runtime-pytest
python -m ruff check nbsr tests scripts tools
python -m ruff format --check nbsr tests scripts tools
python -m pip check
python tools/generate_core_v01_vectors.py --check
python scripts/generate_core_v02_vectors.py --check vectors/core-v0.2
git diff --check
```

Delete only the verified absolute `.wp3-runtime-pytest` directory created by
this task. Record exact result counts after completion.

- [ ] **Step 5: Commit Task 5 and stop for review**

```powershell
git add tests/test_wp3_single_service_runtime_documentation.py docs/protocol/status.md docs/superpowers/plans/2026-07-28-v3.6-protocol-roadmap.md docs/protocol/wp3-single-service-transport-decision.md
git commit -m "docs(wp3): record single-service runtime evidence"
```

Stop for human review. Do not begin origin forwarding, multi-service reuse,
agent integration, or any WP4 task.

## Plan self-review

- **Spec coverage:** Tasks 1-4 cover deterministic vectors, version locking,
  route admission, replay/proof/policy checks, post-accept stream gating, and
  a bounded origin-free test endpoint. Task 5 records evidence and blocks
  scope expansion.
- **Dependency rule:** Task 1 is a hard conformance gate; no socket or route
  task starts if the exact pinned public-API dependencies cannot reproduce the
  checked-in vectors.
- **Type consistency:** `CoreV02Message` feeds `DestinationAdmission`;
  `ActiveChannel` feeds `ControlSession` and `StreamGate`; Quinn types remain
  confined to `quinn_adapter.rs`.
- **Scope:** The plan creates no new protocol value and touches no existing
  Python runtime file. It stops before origin connection and WP4 reuse.
