# WP3 Rust QUIC Handshake Spike Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an isolated Rust crate that proves a bounded QUIC v1 / TLS 1.3 mutual-authentication handshake between an NBSR Source Edge and Destination Edge without implementing route, channel, stream, or origin behavior.

**Architecture:** A standalone `crates/nbsr-transport` library owns the transport-neutral identity/configuration contract and confines Quinn connection handling to one adapter module. rustls validates both certificate chains, x509-parser extracts the already-authenticated leaf SAN for exact configured peer matching, and loopback tests generate an ephemeral private CA and certificates at runtime. Existing Python runtime and frozen protocol surfaces do not import or invoke the crate.

**Tech Stack:** Rust 1.97.1, Quinn 0.11.11, rustls 0.23.43 with the ring provider and TLS 1.3 only, Tokio 1.53.1, x509-parser 0.18.1, and test-only rcgen 0.14.8.

## Global Constraints

- Work only on `codex/nbsr-v3-wp0-wp1`; do not modify or merge `main`.
- Do not push without an explicit user request.
- Use public Quinn and rustls APIs only; no fork, patch, vendored source, unsafe code, or private dependency access.
- Pin every direct dependency exactly and commit `Cargo.lock`.
- Use QUIC v1, TLS 1.3, and exact ALPN `nbsr-quic-1`.
- Require certificate authentication in both directions; one-way TLS is a failure.
- Disable resumption and never invoke `Connecting::into_0rtt`.
- Use loopback and an ephemeral UDP port; tests require no public network, DNS, fixed port, cloud resource, or machine certificate.
- Generate test CA, certificates, and private keys in memory; do not commit or log private material.
- Do not implement or send HELLO, ROUTE, STREAM, ERROR, control-frame, or application data.
- Do not allocate a Route Context, Service Channel, OriginSet selection, Origin Endpoint connection, quota, audit, replay, revocation, or policy state.
- Do not integrate with `NameRelay`, the Windows agent, DNS interception, Synthetic IP handling, or the existing Python runtime.
- Do not change the 17 Core v0.1 message codes, 19 error codes, six D6 schemas, frozen states/transitions, CBOR rules, COSE wrappers, or Core v0.2 vectors.
- Transport errors are internal Rust errors, not additions to the protocol error registry.
- Preserve unrelated untracked paths `.codex-test-temp-w4/`, `.superpowers/`, and `docs/leakguard_phase19_qa_pack/`.

## File map

| File | Responsibility |
|---|---|
| `crates/nbsr-transport/Cargo.toml` | Exact direct dependencies and crate metadata |
| `crates/nbsr-transport/Cargo.lock` | Fully resolved dependency freeze |
| `crates/nbsr-transport/src/lib.rs` | Public transport-neutral exports and `ALPN` |
| `crates/nbsr-transport/src/config.rs` | Roles, identities, peer policy, TLS material, and Quinn/rustls configuration |
| `crates/nbsr-transport/src/error.rs` | Bounded internal failure taxonomy |
| `crates/nbsr-transport/src/quinn_adapter.rs` | Endpoint lifecycle, handshake, peer extraction, and bounded close |
| `crates/nbsr-transport/tests/support/mod.rs` | In-memory test CA and leaf-certificate generation |
| `crates/nbsr-transport/tests/config.rs` | Configuration, role, and dependency-boundary tests |
| `crates/nbsr-transport/tests/handshake.rs` | Real loopback success and negative mTLS tests |
| `tests/test_wp3_rust_transport_isolation.py` | Repository anti-drift and Python-runtime isolation checks |

---

### Task 1: Freeze the Rust crate and transport-neutral policy

**Files:**
- Create: `crates/nbsr-transport/Cargo.toml`
- Create: `crates/nbsr-transport/Cargo.lock`
- Create: `crates/nbsr-transport/src/lib.rs`
- Create: `crates/nbsr-transport/src/config.rs`
- Create: `crates/nbsr-transport/src/error.rs`
- Create: `crates/nbsr-transport/tests/config.rs`

**Interfaces:**
- Produces:
  - `pub const ALPN: &[u8] = b"nbsr-quic-1"`
  - `pub enum EdgeRole { Source, Destination }`
  - `pub struct EdgeIdentity`
  - `pub struct PeerPolicy`
  - `pub enum TransportError`
  - `EdgeIdentity::from_dns_name(value: impl Into<String>) -> Result<Self, TransportError>`
  - `PeerPolicy::new(local_role, expected_peer_role, expected_peer, handshake_timeout, idle_timeout) -> Result<Self, TransportError>`

- [ ] **Step 1: Create crate metadata and a failing public-contract test**

Create `Cargo.toml` with:

```toml
[package]
name = "nbsr-transport"
version = "0.1.0"
edition = "2024"
publish = false

[dependencies]
quinn = { version = "=0.11.11", default-features = false, features = ["runtime-tokio", "rustls-ring"] }
rustls = { version = "=0.23.43", default-features = false, features = ["ring", "std"] }
tokio = { version = "=1.53.1", features = ["rt", "time"] }
x509-parser = { version = "=0.18.1", default-features = false }

[dev-dependencies]
rcgen = { version = "=0.14.8", default-features = false, features = ["crypto", "ring"] }
tokio = { version = "=1.53.1", features = ["macros", "rt-multi-thread", "time"] }
```

Create `tests/config.rs` importing the not-yet-existing API. Tests must show:

```rust
use std::time::Duration;
use nbsr_transport::{EdgeIdentity, EdgeRole, PeerPolicy, TransportError};

#[test]
fn rejects_same_role_peer_before_socket_creation() {
    let peer = EdgeIdentity::from_dns_name("source-edge.test").unwrap();
    let error = PeerPolicy::new(
        EdgeRole::Source,
        EdgeRole::Source,
        peer,
        Duration::from_secs(2),
        Duration::from_secs(5),
    )
    .unwrap_err();
    assert_eq!(error, TransportError::InvalidPeerRole);
}
```

Add separate tests for an invalid DNS identity, zero handshake timeout, zero
idle timeout, Source-to-Destination policy, and Destination-to-Source policy.

- [ ] **Step 2: Run the focused test and confirm RED**

Run:

```powershell
& "$env:USERPROFILE\.cargo\bin\cargo.exe" test --manifest-path crates/nbsr-transport/Cargo.toml --test config
```

Expected: nonzero because `src/lib.rs` and the imported types do not exist.

- [ ] **Step 3: Implement the minimum policy types**

Implement immutable role and identity types. Validate the identity by converting
an owned string with `rustls::pki_types::ServerName::try_from`; retain only DNS
names and reject IP names. `PeerPolicy::new` rejects equal roles and zero
timeouts. `TransportError` implements `Display` with fixed bounded text and
`std::error::Error`; it never stores arbitrary third-party error strings.

- [ ] **Step 4: Run focused tests and confirm GREEN**

Run:

```powershell
& "$env:USERPROFILE\.cargo\bin\cargo.exe" test --manifest-path crates/nbsr-transport/Cargo.toml --test config
& "$env:USERPROFILE\.cargo\bin\cargo.exe" fmt --manifest-path crates/nbsr-transport/Cargo.toml -- --check
git diff --check
```

Expected: all commands exit 0.

- [ ] **Step 5: Commit Task 1**

```powershell
git add crates/nbsr-transport
git commit -m "feat: add isolated Rust transport boundary"
```

---

### Task 2: Build TLS 1.3-only mutual-authentication configuration

**Files:**
- Modify: `crates/nbsr-transport/src/config.rs`
- Modify: `crates/nbsr-transport/src/error.rs`
- Create: `crates/nbsr-transport/tests/support/mod.rs`
- Modify: `crates/nbsr-transport/tests/config.rs`

**Interfaces:**
- Consumes: Task 1 `PeerPolicy`.
- Produces:
  - `pub struct TlsMaterial`
  - `pub struct ClientEndpointConfig`
  - `pub struct ServerEndpointConfig`
  - `build_client_config(policy, material) -> Result<ClientEndpointConfig, TransportError>`
  - `build_server_config(policy, material) -> Result<ServerEndpointConfig, TransportError>`

- [ ] **Step 1: Generate ephemeral test PKI and write failing config tests**

In `tests/support/mod.rs`, use rcgen to create one in-memory CA plus
`source-edge.test` and `destination-edge.test` leaf certificates with DNS SANs.
Return DER certificate chains, private keys, and a `RootCertStore`. Never write
PEM or DER to disk and never implement `Debug` for private-key containers.

Add tests proving:

- Source client config includes its certificate and expects
  `destination-edge.test`;
- Destination server config uses a mandatory `WebPkiClientVerifier`;
- both sides advertise only `nbsr-quic-1`;
- both rustls configs enable TLS 1.3 only;
- server and client stream limits begin at zero;
- session storage is disabled; and
- malformed or empty certificate material returns a bounded `TransportError`.

- [ ] **Step 2: Run tests and confirm RED**

Run the Task 2 tests by exact name:

```powershell
& "$env:USERPROFILE\.cargo\bin\cargo.exe" test --manifest-path crates/nbsr-transport/Cargo.toml --test config mutual
```

Expected: nonzero because TLS material and configuration builders are absent.

- [ ] **Step 3: Implement client configuration**

Use `rustls::ClientConfig::builder_with_provider(Arc::new(ring::default_provider()))`
plus `.with_protocol_versions(&[&rustls::version::TLS13])`,
`.with_root_certificates(...)`, and `.with_client_auth_cert(...)`.
Set:

```rust
rustls_config.alpn_protocols = vec![ALPN.to_vec()];
rustls_config.enable_early_data = false;
rustls_config.resumption = rustls::client::Resumption::disabled();
```

Convert with `quinn::crypto::rustls::QuicClientConfig::try_from`. Apply the
bounded idle timeout and set bidirectional and unidirectional stream limits to
zero in `quinn::TransportConfig`.

- [ ] **Step 4: Implement server configuration**

Build `WebPkiClientVerifier::builder_with_provider(...)` from the configured
roots without `allow_unauthenticated()`. Pass it to
`rustls::ServerConfig::builder_with_provider(...).with_protocol_versions(...)`
then `.with_client_cert_verifier(...)` and `.with_single_cert(...)`. Set only
the exact ALPN and no early-data allowance. Convert through
`QuicServerConfig::try_from` and apply the same bounded idle and zero-stream
transport policy.

- [ ] **Step 5: Run focused tests and confirm GREEN**

Run:

```powershell
& "$env:USERPROFILE\.cargo\bin\cargo.exe" test --manifest-path crates/nbsr-transport/Cargo.toml --test config
& "$env:USERPROFILE\.cargo\bin\cargo.exe" clippy --manifest-path crates/nbsr-transport/Cargo.toml --all-targets -- -D warnings
```

Expected: all tests pass and Clippy exits 0.

- [ ] **Step 6: Commit Task 2**

```powershell
git add crates/nbsr-transport
git commit -m "feat: require TLS 1.3 mutual edge authentication"
```

---

### Task 3: Prove the bounded loopback QUIC handshake

**Files:**
- Create: `crates/nbsr-transport/src/quinn_adapter.rs`
- Modify: `crates/nbsr-transport/src/lib.rs`
- Create: `crates/nbsr-transport/tests/handshake.rs`

**Interfaces:**
- Consumes: Task 2 endpoint configurations.
- Produces:
  - `pub struct TransportListener`
  - `pub struct AuthenticatedConnection`
  - `TransportListener::bind(config, "127.0.0.1:0".parse().unwrap())`
  - `TransportListener::local_addr() -> SocketAddr`
  - `TransportListener::accept_one() -> Result<AuthenticatedConnection, TransportError>`
  - `connect(config, remote) -> Result<AuthenticatedConnection, TransportError>`
  - `AuthenticatedConnection::authenticated_peer() -> &EdgeIdentity`
  - `AuthenticatedConnection::negotiated_alpn() -> &[u8]`
  - `AuthenticatedConnection::close(self) -> Result<(), TransportError>`

- [ ] **Step 1: Write the failing real loopback test**

Generate the ephemeral PKI, bind Destination Edge to `127.0.0.1:0`, and run
accept/connect concurrently under a two-second outer timeout. Assert:

```rust
assert_eq!(source.authenticated_peer().as_str(), "destination-edge.test");
assert_eq!(destination.authenticated_peer().as_str(), "source-edge.test");
assert_eq!(source.negotiated_alpn(), b"nbsr-quic-1");
assert_eq!(destination.negotiated_alpn(), b"nbsr-quic-1");
```

Close both connections and listener, then require bounded idle completion.

- [ ] **Step 2: Run the test and confirm RED**

Run:

```powershell
& "$env:USERPROFILE\.cargo\bin\cargo.exe" test --manifest-path crates/nbsr-transport/Cargo.toml --test handshake valid_mutual
```

Expected: nonzero because `quinn_adapter.rs` does not exist.

- [ ] **Step 3: Implement listener, connect, and authenticated result**

Use `quinn::Endpoint::server` and a client endpoint bound to
`127.0.0.1:0`. Await `Connecting` under `tokio::time::timeout`; never call
`into_0rtt`.

After the connection completes:

1. downcast `handshake_data()` to
   `quinn::crypto::rustls::HandshakeData`;
2. require `protocol == Some(ALPN.to_vec())`;
3. downcast `peer_identity()` to
   `Vec<rustls::pki_types::CertificateDer<'static>>`;
4. require a nonempty chain;
5. parse only the already-authenticated leaf with x509-parser;
6. require exactly one matching DNS SAN for the configured peer; and
7. close and return `PeerIdentityMismatch` before exposing the connection if
   the match fails.

`AuthenticatedConnection` keeps Quinn's connection private and exposes no
stream-opening API. `close` uses an empty bounded reason, then waits for endpoint
idle completion under the configured bound.

- [ ] **Step 4: Run the successful handshake and confirm GREEN**

Run:

```powershell
& "$env:USERPROFILE\.cargo\bin\cargo.exe" test --manifest-path crates/nbsr-transport/Cargo.toml --test handshake valid_mutual -- --exact
```

Expected: one passing real loopback test.

- [ ] **Step 5: Add one failing negative test at a time**

For each case, write and run the failing test before modifying production code:

- unknown client CA;
- unknown server CA;
- missing client certificate;
- expired client certificate;
- expired server certificate;
- Source Edge SAN mismatch;
- Destination Edge SAN mismatch;
- ALPN mismatch;
- zero-duration handshake timeout; and
- peer close during setup.

Each test asserts a bounded `TransportError` variant. No test asserts raw
library text or uses a fake connection.

- [ ] **Step 6: Implement only the missing bounded mappings**

Map certificate/handshake rejection, ALPN rejection, identity rejection,
timeout, peer close, and internal transport failure to closed internal variants.
Discard third-party reason strings. Do not add protocol error values.

- [ ] **Step 7: Run all Rust tests and commit Task 3**

Run:

```powershell
& "$env:USERPROFILE\.cargo\bin\cargo.exe" test --manifest-path crates/nbsr-transport/Cargo.toml
& "$env:USERPROFILE\.cargo\bin\cargo.exe" fmt --manifest-path crates/nbsr-transport/Cargo.toml -- --check
& "$env:USERPROFILE\.cargo\bin\cargo.exe" clippy --manifest-path crates/nbsr-transport/Cargo.toml --all-targets -- -D warnings
```

Expected: every command exits 0.

Commit:

```powershell
git add crates/nbsr-transport
git commit -m "test: prove bounded QUIC mutual-auth handshake"
```

---

### Task 4: Freeze repository isolation and validate the complete spike

**Files:**
- Create: `tests/test_wp3_rust_transport_isolation.py`
- Modify: `docs/protocol/wp3-single-service-transport-decision.md`
- Modify: `docs/protocol/v3.6-decisions.md`
- Modify: `docs/superpowers/plans/2026-07-28-v3.6-protocol-roadmap.md`

**Interfaces:**
- Consumes: the completed Rust crate.
- Produces: repository-visible evidence that the spike is isolated and does not
  authorize Phase E route/channel runtime.

- [ ] **Step 1: Write failing anti-drift tests**

The Python test reads structured Cargo metadata through:

```powershell
& "$env:USERPROFILE\.cargo\bin\cargo.exe" metadata --locked --no-deps --format-version 1 --manifest-path crates/nbsr-transport/Cargo.toml
```

It asserts exact direct dependency versions and checks behaviorally relevant
repository boundaries:

- no Python module imports or invokes the Rust crate;
- `nbsr/name_relay.py` has no Rust transport import, subprocess call, or FFI
  boundary;
- existing Core v0.1 registry/state/schema behavior tests still pass;
- existing Core v0.2 manifest, artifact-hash, and regeneration tests still
  pass;
- no private key or certificate fixture exists below the new crate;
- only `quinn_adapter.rs` contains Quinn connection/endpoint operations; and
- docs say this is a handshake boundary, not production readiness or completed
  WP3 routing.

- [ ] **Step 2: Run the test and confirm RED**

Run:

```powershell
python -m pytest -q tests/test_wp3_rust_transport_isolation.py
```

Expected: nonzero because the decision and roadmap evidence is not yet updated.

- [ ] **Step 3: Update documentation with exact observed scope**

Record the reviewed `aioquic` blocker as superseded implementation evidence,
the approved Quinn/rustls choice, exact dependency versions, exact passing
loopback/negative tests, and unchanged frozen surfaces. Keep WP3 route,
Service Channel, control framing, application streams, OriginSet selection,
and production deployment explicitly gated.

- [ ] **Step 4: Run complete validation**

Run:

```powershell
& "$env:USERPROFILE\.cargo\bin\cargo.exe" test --locked --manifest-path crates/nbsr-transport/Cargo.toml
& "$env:USERPROFILE\.cargo\bin\cargo.exe" fmt --manifest-path crates/nbsr-transport/Cargo.toml -- --check
& "$env:USERPROFILE\.cargo\bin\cargo.exe" clippy --locked --manifest-path crates/nbsr-transport/Cargo.toml --all-targets -- -D warnings
python -m pytest -q tests/test_wp3_rust_transport_isolation.py tests/test_wp3_transport_decision_documentation.py tests/test_v36_documentation.py
python -m pytest -q
python -m ruff check .
python -m ruff format --check .
python -m pip check
python scripts/generate_core_v02_vectors.py --check
git diff --check
```

If the vector script uses a different checked-in command, use the command
documented by its existing test rather than changing the generator.

Expected: every command exits 0; the full Python count may increase only by the
new isolation tests.

- [ ] **Step 5: Review scope and commit Task 4**

Inspect:

```powershell
git diff --name-only HEAD~3
git status --short
git diff --check
```

Confirm that no unrelated untracked path is staged and no existing runtime file
under `nbsr/` changed.

Commit:

```powershell
git add tests/test_wp3_rust_transport_isolation.py docs/protocol/wp3-single-service-transport-decision.md docs/protocol/v3.6-decisions.md docs/superpowers/plans/2026-07-28-v3.6-protocol-roadmap.md
git commit -m "docs: record isolated Rust QUIC handshake evidence"
```

## Final acceptance gate

The spike is complete only if:

- the real loopback handshake mutually authenticates exact Source and
  Destination Edge DNS SAN identities;
- unknown CA, missing client certificate, SAN mismatch, ALPN mismatch, timeout,
  and premature close fail before an authenticated connection is returned;
- no stream API is exposed and no control/application data is exchanged;
- no call to `into_0rtt` exists;
- dependencies are locked and all Rust validation passes;
- the full existing Python suite and protocol vector checks pass;
- frozen Core v0.1 and reviewed Core v0.2 bytes remain unchanged; and
- documentation keeps all remaining WP3 runtime behavior gated.

Stop and return for human review if any public Quinn/rustls API cannot enforce
these conditions without private access or if implementation requires changing
an existing protocol or Python runtime surface.
