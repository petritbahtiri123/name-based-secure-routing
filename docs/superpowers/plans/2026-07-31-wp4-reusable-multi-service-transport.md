# WP4 Reusable Multi-Service Transport Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the WP3 origin-free Rust loopback into a bounded reusable multi-service QUIC Transport Session with independently authorized TCP and UDP Service Channels, exporter binding, lifecycle isolation, and same-edge resumption.

**Architecture:** Keep one authenticated Core v0.2 control session and replace its single-route state with a bounded channel registry. Each channel owns its authorization, exporter context, stream/datagram gates, quotas, audit state, drain/revocation state, and resume eligibility; Quinn types remain isolated in `quinn_adapter.rs`.

**Tech Stack:** Rust 2024, Quinn 0.11.11, rustls 0.23.43, Tokio 1.53.1, deterministic CBOR, SHA-256, TLS 1.3 exporters, QUIC DATAGRAM, Python documentation/conformance tests.

## Global Constraints

- Do not touch `main`, merge, or push.
- Never stage or access `.codex-test-temp-w4/`.
- Preserve every WP3 non-claim and frozen Core v0.1 D1-D6 boundary.
- Do not add OriginSet selection, Origin Endpoint connection, NameRelay integration, production claims, cross-edge resume, 0-RTT, HTTP/3, MASQUE, or CONNECT-UDP.
- Keep all Quinn connection, stream, exporter, and datagram operations in `crates/nbsr-transport/src/quinn_adapter.rs`.
- Use a non-OneDrive `CARGO_TARGET_DIR` for fresh Rust runs.
- Start every runtime task with a focused failing regression test.
- Commit code separately from final evidence documentation.

---

### Task 1: Freeze the approved WP4 decision and anti-drift contract

**Files:**
- Create: `docs/protocol/wp4-reusable-multi-service-transport-decision.md`
- Create: `tests/test_wp4_transport_decision_documentation.py`
- Modify: `docs/protocol/status.md`
- Modify: `docs/superpowers/plans/2026-07-28-v3.6-protocol-roadmap.md`

**Interfaces:**
- Consumes: approved design at `docs/superpowers/specs/2026-07-31-wp4-reusable-multi-service-transport-design.md`.
- Produces: exact textual gates and limits checked before runtime changes.

- [ ] **Step 1: Write the failing documentation test** asserting the decision contains the reuse tuple, single-use RouteGrant rule, exporter label/context fields, all exact limits, native QUIC DATAGRAM choice, 30-second drain, same-edge-only resume, all non-claims, and no frozen Core v0.1 changes.
- [ ] **Step 2: Run `python -m pytest tests/test_wp4_transport_decision_documentation.py -q`** and verify failure because the protocol decision is absent.
- [ ] **Step 3: Copy the approved design into the protocol decision** and update status/roadmap only to mark WP4 implementation approved and in progress—not implemented.
- [ ] **Step 4: Run the focused documentation test and frozen registry/schema/state/vector tests** and verify pass.
- [ ] **Step 5: Commit only decision and documentation-test files** with `docs(wp4): approve reusable multi-service transport`.

### Task 2: Replace the single-route session state with a bounded channel registry

**Files:**
- Create: `crates/nbsr-transport/src/channel_registry.rs`
- Create: `crates/nbsr-transport/tests/multi_channel.rs`
- Modify: `crates/nbsr-transport/src/session.rs`
- Modify: `crates/nbsr-transport/src/admission.rs`
- Modify: `crates/nbsr-transport/src/lib.rs`

**Interfaces:**
- Produces: `ChannelRegistry::new(ChannelLimits)`, `admit_pending`, `confirm_active`, `channel`, `channel_mut`, and `remove`; `ControlSession::accept_route_open` and `confirm_route_accept` support repeated correlated exchanges.

- [ ] **Step 1: Add failing tests** proving two different services with fresh grants share one HELLO session, duplicate channel/grant nonce fails, per-session 33rd channel fails, per-service ninth channel fails, and a rejected channel leaves siblings unchanged.
- [ ] **Step 2: Run `cargo test --locked --manifest-path crates/nbsr-transport/Cargo.toml --test multi_channel`** and verify RED against the single-route state machine.
- [ ] **Step 3: Implement `ChannelRegistry`** with 32-session/8-service bounds, pending request correlation, retained replay sets, and independently owned `ActiveChannel` records.
- [ ] **Step 4: Refactor `ControlSession`** so HELLO state is session-wide while ROUTE exchanges mutate registry entries rather than a global `RouteAccepted` state.
- [ ] **Step 5: Run multi-channel, control, admission, route-context, and stream-gate tests** and verify pass.
- [ ] **Step 6: Commit** with `feat(wp4): admit isolated service channels`.

### Task 3: Support multiple independently gated reliable streams

**Files:**
- Create: `crates/nbsr-transport/src/channel_streams.rs`
- Create: `crates/nbsr-transport/tests/multi_stream.rs`
- Modify: `crates/nbsr-transport/src/stream_gate.rs`
- Modify: `crates/nbsr-transport/src/session.rs`
- Modify: `crates/nbsr-transport/src/quinn_adapter.rs`
- Modify: `crates/nbsr-transport/src/lib.rs`

**Interfaces:**
- Produces: `ChannelStreams::authorize_open(channel_id, envelope)`, `confirm_accept`, `authorize_application_stream`, `release`, and bounded byte reservations.

- [ ] **Step 1: Add failing tests** for stream IDs 4, 8, and 12 on different/same channels; 64-stream channel capacity; 1 MiB stream and 8 MiB channel buffering; pre-accept/oversize resets; and sibling delivery after one channel fails.
- [ ] **Step 2: Run the focused multi-stream/application-stream tests** and verify RED because WP3 hard-codes stream ID 4 and one gate.
- [ ] **Step 3: Implement per-channel stream maps and quota accounting** while retaining exact `STREAM_OPEN`/`STREAM_ACCEPT` correlation and actual Quinn stream-ID checks.
- [ ] **Step 4: Extend the Quinn loopback harness** to open multiple application streams without moving Quinn types outside the adapter.
- [ ] **Step 5: Run all Rust stream/control tests** and verify pass.
- [ ] **Step 6: Commit** with `feat(wp4): multiplex isolated tcp streams`.

### Task 4: Freeze exporter derivation and independent vectors

**Files:**
- Create: `docs/protocol/core-v0.2-service-channel-exporter.md`
- Create: `vectors/core-v0.2/wp4-exporter/manifest.json`
- Create: `scripts/generate_wp4_exporter_vectors.py`
- Create: `scripts/verify_wp4_exporter_vectors.mjs`
- Create: `tests/test_wp4_exporter_vectors.py`
- Create: `crates/nbsr-transport/tests/exporter_vectors.rs`

**Interfaces:**
- Produces: canonical context bytes, SHA-256 context digest, fixed TLS handshake fixture inputs, and expected 32-byte exporter results for label `EXPORTER-NBSR-Service-Channel-v2`.

- [ ] **Step 1: Add failing Python manifest/regeneration/Node-verifier tests** for valid vectors and one-field mutations across every context input.
- [ ] **Step 2: Run the focused Python tests** and verify RED because no WP4 vectors exist.
- [ ] **Step 3: Implement deterministic vector generation** using fixed TLS 1.3 fixture secrets and RFC 8446 HKDF-Expand-Label semantics; never invent live exporter output.
- [ ] **Step 4: Implement the dependency-independent Node verifier** and require byte-for-byte agreement on context encoding, digest, and exporter output.
- [ ] **Step 5: Add Rust decoding/derivation tests** consuming exactly the checked-in manifest.
- [ ] **Step 6: Run regeneration, Python, Node, and Rust vector tests** and verify pass.
- [ ] **Step 7: Commit** with `feat(wp4): freeze service channel exporter vectors`.

### Task 5: Bind live channels to the rustls exporter

**Files:**
- Create: `crates/nbsr-transport/src/channel_binding.rs`
- Create: `crates/nbsr-transport/tests/channel_binding.rs`
- Modify: `crates/nbsr-transport/src/quinn_adapter.rs`
- Modify: `crates/nbsr-transport/src/session.rs`
- Modify: `crates/nbsr-transport/src/admission.rs`
- Modify: `crates/nbsr-transport/src/lib.rs`

**Interfaces:**
- Produces: `ChannelBindingContext::encode`, `AuthenticatedConnection::export_channel_binding`, and an opaque redacted `ChannelBinding` stored on the active channel.

- [ ] **Step 1: Add failing tests** proving both loopback peers derive identical bindings and every session/edge/channel/route/grant/service/transport/port/policy/nonce mutation differs or rejects.
- [ ] **Step 2: Run channel-binding tests** and verify RED because exporter access is absent.
- [ ] **Step 3: Implement canonical context construction** exactly as the approved decision and validate all lengths/types before exporter invocation.
- [ ] **Step 4: Expose rustls exporter output only through `AuthenticatedConnection`** in `quinn_adapter.rs`; never expose TLS/Quinn types or log the value.
- [ ] **Step 5: Require binding creation after correlated ROUTE_ACCEPT and before any stream gate**.
- [ ] **Step 6: Run exporter, session, stream, and handshake tests** and verify pass.
- [ ] **Step 7: Commit** with `feat(wp4): bind channels to tls exporter`.

### Task 6: Add per-channel audit, revocation, and failure containment

**Files:**
- Create: `crates/nbsr-transport/src/channel_lifecycle.rs`
- Create: `crates/nbsr-transport/src/audit.rs`
- Create: `crates/nbsr-transport/tests/channel_lifecycle.rs`
- Modify: `crates/nbsr-transport/src/channel_registry.rs`
- Modify: `crates/nbsr-transport/src/channel_streams.rs`
- Modify: `crates/nbsr-transport/src/session.rs`
- Modify: `crates/nbsr-transport/src/lib.rs`

**Interfaces:**
- Produces: `ChannelState::{Active,Draining,Revoked,Closed}`, `AuditQueue` capped at 1024, 4096-entry replay/tombstone store, and channel-scoped revoke/close operations.

- [ ] **Step 1: Add failing tests** for mandatory audit-before-mutation, redacted records, monotonic audit sequence, 1024-event exhaustion, 4096 replay entries, terminal revocation, and sibling survival.
- [ ] **Step 2: Run focused lifecycle tests** and verify RED.
- [ ] **Step 3: Implement bounded audit and tombstone stores** that reject state-changing work on uncertain capacity.
- [ ] **Step 4: Implement revoke/close transitions** and reset only the target channel's streams.
- [ ] **Step 5: Run lifecycle plus multi-channel/multi-stream tests** and verify pass.
- [ ] **Step 6: Commit** with `feat(wp4): contain channel lifecycle failures`.

### Task 7: Add bounded channel and session drain

**Files:**
- Create: `docs/protocol/core-v0.2-channel-lifecycle-schema-proposal.md`
- Create: `crates/nbsr-transport/tests/drain.rs`
- Modify: `crates/nbsr-transport/src/core_v02.rs`
- Modify: `crates/nbsr-transport/src/channel_lifecycle.rs`
- Modify: `crates/nbsr-transport/src/session.rs`
- Modify: `crates/nbsr-transport/src/quinn_adapter.rs`

**Interfaces:**
- Produces: closed deterministic Core v0.2 candidate bodies for existing `ROUTE_DRAIN`, `ROUTE_REVOKE`, and `ROUTE_CLOSE`; 30-second monotonic drain deadlines.

- [ ] **Step 1: Add failing deterministic-body and fake-clock tests** proving drain stops new work immediately, existing TCP completes before 30 seconds, forced reset occurs at the deadline, and no lifetime is extended.
- [ ] **Step 2: Run focused drain tests** and verify RED.
- [ ] **Step 3: Document and encode the closed numeric-key lifecycle bodies** without changing Core v0.1 registries.
- [ ] **Step 4: Implement channel and session drain using injected monotonic time** and adapter-confined resets/connection close.
- [ ] **Step 5: Run drain, lifecycle, multi-stream, and frozen-protocol tests** and verify pass.
- [ ] **Step 6: Commit** with `feat(wp4): bound channel and session drain`.

### Task 8: Add fail-closed same-edge resumption

**Files:**
- Create: `crates/nbsr-transport/src/resumption.rs`
- Create: `crates/nbsr-transport/tests/resumption.rs`
- Modify: `crates/nbsr-transport/src/session.rs`
- Modify: `crates/nbsr-transport/src/channel_registry.rs`
- Modify: `crates/nbsr-transport/src/lib.rs`

**Interfaces:**
- Produces: `ResumeStore` with 32-byte opaque single-use handles, 30-second retention, atomic consume, and exact same-edge/trust/ALPN/version bindings.

- [ ] **Step 1: Add failing tests** for successful same-edge correlation with fresh grant/session/channel/nonces/exporter and rejection on replay, expiry, revocation, drain, policy/service/key mismatch, or either edge change.
- [ ] **Step 2: Run focused resumption tests** and verify RED.
- [ ] **Step 3: Implement bounded handle issuance/consumption** without restoring old authority or allowing 0-RTT.
- [ ] **Step 4: Integrate resumption only after complete fresh route admission** and ensure cross-edge attempts create no channel.
- [ ] **Step 5: Run resumption, lifecycle, exporter, and multi-channel tests** and verify pass.
- [ ] **Step 6: Commit** with `feat(wp4): resume channels on the same edge`.

### Task 9: Add bounded native QUIC DATAGRAM channels

**Files:**
- Create: `docs/protocol/core-v0.2-udp-datagram-schema-proposal.md`
- Create: `crates/nbsr-transport/src/datagram_gate.rs`
- Create: `crates/nbsr-transport/tests/datagram.rs`
- Modify: `crates/nbsr-transport/src/core_v02.rs`
- Modify: `crates/nbsr-transport/src/admission.rs`
- Modify: `crates/nbsr-transport/src/channel_registry.rs`
- Modify: `crates/nbsr-transport/src/quinn_adapter.rs`
- Modify: `crates/nbsr-transport/src/lib.rs`

**Interfaces:**
- Produces: canonical closed CBOR datagram body, `DatagramGate` with per-direction monotonic sequence, 1200-byte inner cap, 64 queued datagrams, and 100/s burst-200 token bucket.

- [ ] **Step 1: Add failing schema/vector tests** for canonical body bytes, wrong channel/transport, replay/order, unknown fields, oversize, and non-canonical CBOR.
- [ ] **Step 2: Add failing loopback/quota tests** proving one datagram maps to one payload, no fragmentation, drop-on-quota audit, and sibling containment.
- [ ] **Step 3: Run focused datagram tests** and verify RED.
- [ ] **Step 4: Implement canonical framing and `DatagramGate`** after allocating exact Core v0.2 candidate body keys in the approved schema document only.
- [ ] **Step 5: Add Quinn DATAGRAM send/receive inside the adapter** and enforce the smaller of 1200 bytes or peer/path capacity after framing.
- [ ] **Step 6: Run datagram, lifecycle, exporter, and multi-channel tests** and verify pass.
- [ ] **Step 7: Commit** with `feat(wp4): carry isolated udp datagrams`.

### Task 10: Fresh validation, independent review, fixes, and evidence

**Files:**
- Modify: `docs/protocol/status.md`
- Modify: `docs/protocol/wp4-reusable-multi-service-transport-decision.md`
- Modify: `docs/protocol/resource-timeout-profile.md`
- Modify: `docs/superpowers/plans/2026-07-28-v3.6-protocol-roadmap.md`
- Create: `tests/test_wp4_runtime_documentation.py`

**Interfaces:**
- Consumes: all WP4 code and focused test evidence.
- Produces: reviewed completion record limited to the origin-free loopback lab.

- [ ] **Step 1: Run fresh Rust validation**: locked full suite, Rustfmt check, and Clippy all-targets with `-D warnings`, using a non-OneDrive Cargo target.
- [ ] **Step 2: Run focused WP4 and frozen-protocol Python tests**, then the full Python suite with a writable isolated `--basetemp`.
- [ ] **Step 3: Run Ruff check/format, `pip check`, Core v0.1 and Core v0.2 regeneration checks, Node verifier, and `git diff --check`**.
- [ ] **Step 4: Dispatch independent review** for Critical/Important authorization, exporter, lifecycle, quota, audit, drain, resume, UDP, isolation, privacy, and frozen-wire findings.
- [ ] **Step 5: Fix every Critical/Important finding with a failing regression test first**, rerun affected focused tests, and commit fixes separately.
- [ ] **Step 6: Write a failing runtime-documentation test** requiring exact fresh counts and every retained non-claim.
- [ ] **Step 7: Record only freshly observed evidence** and verify the documentation test plus `git diff --check`.
- [ ] **Step 8: Commit evidence only** with `docs(wp4): record reusable transport evidence`.
- [ ] **Step 9: Reconfirm branch, HEAD, `main`, clean staging/worktree, and ignored `.codex-test-temp-w4/`**; do not merge or push.

## Plan self-review

- **Spec coverage:** Tasks 2-3 cover multi-service TCP; Tasks 4-5 exporter inputs/vectors/live binding; Task 6 authorization, revocation, audit, quotas, and containment; Task 7 exact drain; Task 8 same-edge-only resume; Task 9 UDP; Task 10 independent review and fresh evidence.
- **Scope:** Origin selection/connection, NameRelay, cross-edge continuity, production packaging, HTTP/3/MASQUE, 0-RTT, and frozen Core v0.1 changes remain excluded.
- **Type consistency:** `ChannelRegistry` owns `ActiveChannel`; `ChannelStreams`, lifecycle, resumption, and datagram gates all address the same `[u8; 16] channel_id`; Quinn/rustls objects remain adapter-private.
- **No placeholders:** Every task names exact files, test intent, limits, interfaces, commands, and commit boundary.

