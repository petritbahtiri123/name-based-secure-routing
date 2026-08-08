# WP8 Task 10 Live Federation Interoperability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan sequentially. Do not parallelize authority-consuming implementation tasks. Independent reviewers are dispatched only after the implementation diff is complete.

**Goal:** Bind verified Federation v0.1 authority to the existing Rust/Quinn `nbsr/1` route and stream path, prove a live deterministic two-operator route, attempt genuine independent wire interoperability without changing frozen authority, and publish reproducible WP8 closure evidence.

**Architecture:** Python remains the Federation reference authority and composes the existing WP7 operator model. Rust consumes a sealed, typed, non-serialized `VerifiedFederationAuthorization` beside the immutable RouteGrant and gates the existing Transport Session, Route Context, Service Channel, and Application Stream. Node and Task 9 Go remain verifier-only; a separate minimal independent wire peer is attempted only if it can reproduce the frozen `nbsr/1` protocol without new semantics or material architecture.

**Tech Stack:** Python 3.14, pytest, cryptography, Rust 2024, Quinn 0.11.11, rustls 0.23.43, Tokio 1.53.1, Go 1.26.5, Node.js, deterministic CBOR, COSE Sign1/Ed25519, Windows `pktmon`.

## Global Constraints

- Starting baseline is exactly `7af982239dc8fbc67ae142037f192458c797f4d4` on `codex/nbsr-v3-wp0-wp1`, with matching origin and a clean tree except the approved Task 10 design and plan while work is in progress.
- Preserve every approved Core v0.1/Core v0.2 and Federation v0.1 Development Profile literal, authority, vector, registry, schema, message, transcript, and failure rule.
- Allocate no new wire object, message code, field, transcript, serialization, capability, authority, or fallback.
- `VerifiedFederationAuthorization` is internal, typed, sealed, and non-wire. Runtime construction from JSON, debug metadata, expected results, or unchecked bytes is forbidden.
- Source admission precedes independent destination admission. No application payload is forwarded until federation, route, channel, and stream admission all succeed.
- Node and `verifiers/federation-go` remain independent conformance verifiers only.
- Independent route/stream wire interoperability requires a genuinely independent peer. Same-Rust peer exchange does not satisfy it.
- If an independent peer requires new semantics or material architecture, do not implement it; report `NOT YET PROVEN` and continue independently valid Task 10 evidence work. Stop only if the contradiction affects the existing Rust/native path or another remaining task requires changing frozen authority.
- Real public-safe packet capture is mandatory for Task 10 acceptance. An unobservable or privacy-unsafe capture is a blocker.
- Follow literal RED → observed expected failure → minimal GREEN for every behavior change.
- Do not edit frozen vectors except to add Task 10-owned evidence outside `vectors/federation-v0.1/`; generator check must prove the Task 7 package remains byte-identical.
- Do not run latency/performance benchmarking, deployment expansion, demos, or new protocol work.
- Keep all Task 10 changes in one final commit named `feat(wp8): complete live federation interoperability`; no intermediate commits and no push.

---

## File structure

| Path | Responsibility |
|---|---|
| `nbsr/federation/live_lab.py` | Compose authenticated Federation decisions into the existing WP7 two-operator administrative model |
| `tests/federation/test_live_interoperability.py` | Python RED/GREEN success, malicious state, rotation, rollback, and split-view behavior |
| `crates/nbsr-transport/src/federation.rs` | Sealed typed non-wire Rust federation authorization boundary |
| `crates/nbsr-transport/tests/federation.rs` | Rust binding, construction, mismatch, expiry, revocation, replay, and downgrade tests |
| `crates/nbsr-transport/tests/live_federation.rs` | Live same-implementation two-operator Quinn route/channel/stream proof |
| `interop/nbsr-go-peer/` | Conditional independent Go QUIC/TLS `nbsr/1` peer, separate from the Task 9 verifier |
| `tests/federation/test_independent_wire_peer.py` | Cross-process Rust ↔ independent-peer exchange and claim gate |
| `scripts/capture_wp8_live_interop.ps1` | Narrow `pktmon` capture lifecycle and conversion |
| `evidence/wp8-task10/` | Public-safe capture, machine-readable result summary, digest inventory, and review reports |
| `scripts/verify_wp8_conformance.py` | Manifest-first public conformance orchestration and exact accounting |
| `tests/federation/test_wp8_conformance_runner.py` | Runner failure propagation, counting, skips, manifest-first, and drift tests |
| `docs/protocol/federation-v0.1-wire.md` | Implemented Federation v0.1 object/control and transport-binding reference |
| `docs/protocol/wp8-federation-v0.1-decision.md` | Task 10 decision, evidence tiers, reviews, and non-claims |
| `docs/internet-drafts/draft-nbsr-federation-00.md` | Public implementation-derived protocol draft |
| `docs/protocol/wp8-task10-packet-capture.md` | Capture procedure, visible metadata, privacy review, and inference limits |
| `tests/federation/test_runtime_documentation.py` | Documentation consistency and honest claim-tier tests |

### Task 1: Reconfirm baseline and independent-peer inventory

**Files:**
- Modify: `docs/superpowers/specs/2026-08-08-wp8-task10-live-federation-interoperability-design.md` only if inventory evidence corrects a factual statement
- Modify: this plan only if exact paths differ from the repository

**Interfaces:**
- Consumes: Git baseline and existing language/runtime inventory.
- Produces: an explicit go/no-go record for production work and the independent-peer attempt.

- [ ] Run exact Git preflight and stop unless path, branch, local HEAD, remote tip, merge base, and clean baseline match the Global Constraints.
- [ ] Search non-document code for `nbsr/1`, `CLIENT_HELLO`, `ROUTE_OPEN`, `STREAM_OPEN`, QUIC connection APIs, and application payload framing.
- [ ] Record the result: Rust is the only current live peer; Python and Node Core tools are deterministic semantics/verifier implementations; Node and Go Federation tools are verifier-only.
- [ ] Inspect available Go/Node/Python QUIC libraries and the frozen Rust TLS identity/ALPN/control framing surface without adding dependencies.
- [ ] Determine whether a minimal genuinely independent `nbsr/1` wire peer is feasible solely from frozen authority and existing protocol artifacts.
- [ ] If feasibility requires new wire semantics, transcript layout, serialization, authority, capability, registry allocation, or material architecture expansion, do not implement the independent peer and record `independent route/stream wire interoperability: NOT YET PROVEN`. This blocks WP8 evidence closure, but it does not automatically block independently valid remaining Task 10 evidence work.
- [ ] Continue with authenticated Federation-to-WP7 integration, the sealed Rust boundary, live same-Rust federation, drills, packet capture, conformance, documentation, and reviews unless one of those tasks requires changing frozen authority or the feasibility investigation reveals a contradiction affecting the existing Rust/native path.
- [ ] Keep the final report's live two-operator federation integration, independent federation semantic verification, and independent route/stream wire interoperability results separate. Never declare WP8 evidence-closed while the third result is `NOT YET PROVEN`.

### Task 2: Feed authenticated Federation decisions into the WP7 operator model

**Files:**
- Create: `nbsr/federation/live_lab.py`
- Create: `tests/federation/test_live_interoperability.py`
- Modify: `nbsr/federation/__init__.py`

**Interfaces:**
- Consumes: `AuthenticatedBilateralContext`, `BilateralAuthorizer`, `AuthorizationEvidence`, and `OperatorPairRuntime`.
- Produces: `LiveFederationAdmission.authorize(context, source_evidence, destination_evidence, route) -> VerifiedLiveFederationRoute` with no public constructor for the verified result.

- [ ] Write a success RED test using two distinct Operator IDs, exact-purpose signing authorities, separate trust and policy state, a valid authenticated bilateral context, source-first authorization, and destination authorization. The missing `LiveFederationAdmission` must be the failure.
- [ ] Run `python -m pytest -q tests/federation/test_live_interoperability.py::test_valid_cross_operator_federation_authorizes_wp7_route` and observe the expected missing-interface failure.
- [ ] Implement the smallest composition layer. The verified result contains canonical typed bindings and the exact authenticated context digest; it contains no Origin Endpoint or descriptive expected-result field.
- [ ] Run the focused success test and observe PASS.
- [ ] Add one RED parameterized test per required failure: untrusted operator, wrong Operator ID, wrong signing key, wrong `kid`, wrong purpose, wrong service/class authority, expired authority, revoked authority, stale generation/sequence, rollback, equivocation/split view, incomplete trust bundle, source-minted destination authority, and destination-minted owner authority.
- [ ] Run the focused file and confirm each new case fails for missing validation, then implement minimal fail-closed validation and rerun to PASS.
- [ ] Add RED rotation drills for safe operational signer rotation, safe trust-bundle rotation, revoked old key, new-key activation, stale bundle/ownership, conflicting generation, and compromised signer removal; implement only the adapter behavior needed to make them pass.
- [ ] Run `python -m pytest -q tests/federation/test_live_interoperability.py` and record the exact count.

### Task 3: Add the sealed Rust federation authorization boundary

**Files:**
- Create: `crates/nbsr-transport/src/federation.rs`
- Create: `crates/nbsr-transport/tests/federation.rs`
- Modify: `crates/nbsr-transport/src/lib.rs`
- Modify: `crates/nbsr-transport/src/admission.rs`
- Modify: `crates/nbsr-transport/src/session.rs`

**Interfaces:**
- Produces: `VerifiedFederationAuthorization`, `FederationAuthorizationInput`, and `FederationReject`.
- Consumes: typed source/destination Operator IDs, service ID, transport, port, context digests, validity, version, dependency set/digest, and status.
- `DestinationAdmission::admit_federated` and `ControlSession::accept_federated_route_open` require both the existing RouteGrant inputs and a borrowed verified authorization.

- [ ] Write a compile/behavior RED test proving external callers cannot construct `VerifiedFederationAuthorization` directly and that the existing route path rejects when federation is required but absent.
- [ ] Run `cargo test --manifest-path crates/nbsr-transport/Cargo.toml --test federation` with a writable non-OneDrive `CARGO_TARGET_DIR`; observe the expected missing-module/API failure.
- [ ] Implement the private-field type and validating module constructor. Validate fixed lengths, exact source/destination/service/transport/port bindings, inclusive-not-after time rules already frozen by Federation, accepted state, affected version, sorted unique dependencies, and dependency digest.
- [ ] Rerun the focused Rust test and observe PASS.
- [ ] Add RED cases for stale context, rejected ownership/delegation, revoked dependency, untrusted peer, wrong destination operator, service, transport, port/capability, replay, expired authority, unsupported profile, static downgrade, and mismatched route-context digest.
- [ ] Implement the minimal gate beside the immutable RouteGrant. Do not edit Core message encoding or RouteGrant validation.
- [ ] Add RED selective-invalidation tests proving only dependent candidate/active channels are denied or enforced under the frozen mode and sibling channels remain isolated.
- [ ] Run the focused Rust test after every GREEN and then run existing `admission`, `route_context`, `stream_gate`, `multi_channel`, `channel_binding`, and `application_stream` tests.

### Task 4: Prove the live same-implementation two-operator Quinn path

**Files:**
- Create: `crates/nbsr-transport/tests/live_federation.rs`
- Modify: `crates/nbsr-transport/tests/support/mod.rs` only for reusable live test setup

**Interfaces:**
- Consumes: the Task 3 typed authorization and existing Quinn listener/client, control-session, channel-binding, and application-stream APIs.
- Produces: one deterministic live route result with explicit claim tier `shared-rust-transport`.

- [ ] Write a RED integration test that creates separate source/destination identities and policies, establishes authenticated `nbsr/1`, binds the verified Federation context, completes HELLO/ROUTE/STREAM exchanges, and transfers the literal safe payload `NBSR-WP8-TASK10-LIVE-v1`.
- [ ] Run the focused live test and observe rejection at the missing federation gate.
- [ ] Add the smallest live plumbing needed to pass; do not add an alternate control path.
- [ ] Add RED tests proving zero payload delivery before destination authorization, route acceptance, channel exporter binding, or stream acceptance.
- [ ] Add RED live rejection cases for wrong peer, wrong service/transport/port, expired context, revoked dependency, replay, and downgrade; make each pass through the Task 3 gate.
- [ ] Verify original HTTPS/SNI/certificate semantics only if the existing test surface actually supports an application TLS fixture. Otherwise record it as unsupported, not passed.
- [ ] Run `cargo test --manifest-path crates/nbsr-transport/Cargo.toml --test live_federation -- --nocapture` and record exact tests and deterministic payload result.

### Task 5: Build and gate a genuinely independent wire peer

**Files:**
- Create conditionally: `interop/nbsr-go-peer/go.mod`
- Create conditionally: `interop/nbsr-go-peer/cmd/peer/main.go`
- Create conditionally: focused packages under `interop/nbsr-go-peer/internal/` for strict CBOR, Core messages, RouteGrant/PoP, TLS identity, framing, and peer state
- Create: `tests/federation/test_independent_wire_peer.py`
- Create: `evidence/wp8-task10/independent-wire-peer.json`

**Interfaces:**
- Consumes: frozen Core v0.2 documents, registries, vectors, public test certificates/keys, and live Rust endpoint configuration.
- Produces: independent process exchange result containing roles, exact frozen messages exchanged, payload digest, and zero divergence. It must never consume Rust code or expected-result labels.

- [ ] Write a RED cross-process test that starts a Rust peer and an independent peer, completes `CLIENT_HELLO` through `STREAM_ACCEPT`, transfers the fixed safe payload, and verifies the returned digest.
- [ ] Run the test and observe the expected missing-independent-peer failure.
- [ ] Implement only after confirming the independent QUIC/TLS library can reproduce the frozen ALPN, certificate identity, control stream, deterministic CBOR, RouteGrant signature, PoP transcript, correlation, and stream binding without protocol changes.
- [ ] Build strict parsers and state transitions from literals and vectors, with focused unit RED/GREEN cycles for every message before live exchange.
- [ ] Add role reversal if the frozen roles and independent implementation support both client and server without new architecture; otherwise state the exact supported direction and do not claim role reversal.
- [ ] Add mutation tests for relabeled expected output, wrong request ID, wrong stream ID, wrong peer identity, wrong proof signature, payload-before-accept, malformed/over-limit CBOR, and unsupported version.
- [ ] Run Go unit tests/vet and the cross-process test. If the independent exchange needs new wire semantics or material architecture, do not implement that peer, record independent wire interoperability as `NOT YET PROVEN`, and continue independently valid evidence work. Stop for human review only if the discovered contradiction also affects the existing Rust/native path.

### Task 6: Produce and privacy-review real packet evidence

**Files:**
- Create: `scripts/capture_wp8_live_interop.ps1`
- Create: `docs/protocol/wp8-task10-packet-capture.md`
- Create after successful capture: `evidence/wp8-task10/live-federation.pcapng`
- Create: `evidence/wp8-task10/capture-manifest.json`
- Create: `tests/federation/test_packet_evidence.py`

**Interfaces:**
- Consumes: the live Task 4 flow and, if completed, Task 5 independent flow.
- Produces: public-safe capture plus digest/flow/privacy metadata, never key material.

- [ ] Write RED tests requiring a real non-empty recognized capture, exact SHA-256/length inventory, approved loopback/test endpoints only, and absence of private keys, credentials, raw subscriber identifiers, protected Origin Endpoint literals, or plaintext payload.
- [ ] Implement a PowerShell capture wrapper that resolves exact executable paths, starts scoped `pktmon`, runs one live test flow, stops capture reliably, converts to `pcapng`, and reports non-zero on any missing/empty/unconvertible artifact.
- [ ] Execute the wrapper. Inspect the capture metadata and packets with available local tooling; do not infer authorization from ciphertext.
- [ ] If the actual flow is not captured or privacy cannot be demonstrated, stop and report packet capture as an acceptance blocker.
- [ ] Write the capture document with procedure, flow boundary, visible metadata, QUIC/TLS protection, privacy exclusions, and ciphertext inference limits.
- [ ] Run the focused packet-evidence tests and record exact results.

### Task 7: Add the public conformance entrypoint

**Files:**
- Create: `scripts/verify_wp8_conformance.py`
- Create: `tests/federation/test_wp8_conformance_runner.py`
- Create after final run: `evidence/wp8-task10/conformance-result.json`

**Interfaces:**
- Produces: deterministic JSON summary with each command, exit status, exact pass/fail/skip counts, duration as non-normative usability data, and claim tier.

- [ ] Write RED tests using controlled child commands to prove manifest verification runs first, failure stops with non-zero status, skips are explicit, counts are parsed or marked unavailable rather than invented, and generated drift fails.
- [ ] Implement the runner with an explicit command table and bounded subprocess output. Do not invoke public DNS/Internet.
- [ ] Add the real command matrix for Federation generator check, schema/threshold literals, Python Federation/full suites, Node Federation/Core verifiers, Go verifier tests/vet/run, Rust fmt/clippy/tests, WP4 exporter verifier, WP7 verifier, Task 10 live/independent/capture tests, Ruff, `pip check`, dependency inspection, privacy scan, documentation tests, and `git diff --check`.
- [ ] Run controlled focused tests to GREEN.
- [ ] Run the real entrypoint only after Tasks 2-6 pass; write the result atomically and fail if rerunning changes deterministic fields other than explicitly non-normative timing.

### Task 8: Publish the public draft and honest closure evidence

**Files:**
- Create: `docs/protocol/federation-v0.1-wire.md`
- Create: `docs/protocol/wp8-federation-v0.1-decision.md`
- Create: `docs/internet-drafts/draft-nbsr-federation-00.md`
- Create: `tests/federation/test_runtime_documentation.py`
- Modify: `docs/protocol/status.md`
- Modify: `README.md`
- Modify: `docs/superpowers/plans/2026-07-28-v3.6-protocol-roadmap.md`

**Interfaces:**
- Consumes: observed Task 10 evidence only.
- Produces: consistent normative reference, public draft, implementation status, evidence tier, and non-claims.

- [ ] Write documentation RED tests that parse headings/tables and require accurate implementation roles, live lab result, independent wire result, capture inventory, conformance command, review results, and all mandatory non-claims.
- [ ] Run focused documentation tests and observe missing-artifact failures.
- [ ] Write the protocol reference and public draft from frozen authority and observed implementation. Separate normative requirements, evidence, deployment guidance, and future work.
- [ ] Update status/README/roadmap only to the strongest observed tier. If Task 5 failed, state `independent route/stream wire interoperability: NOT YET PROVEN` and do not mark WP8 evidence-closed.
- [ ] Run focused documentation tests to GREEN and run `git diff --check`.

### Task 9: Independent correctness and security/privacy reviews

**Files:**
- Create: `evidence/wp8-task10/correctness-review.md`
- Create: `evidence/wp8-task10/security-privacy-review.md`
- Modify: implementation/tests only for confirmed findings through new RED tests

**Interfaces:**
- Produces: independent `READY` or blocking dispositions with exact reviewed baseline/diff and reproduced evidence.

- [ ] Dispatch one independent correctness/interoperability reviewer over `7af9822..working-tree`, the design, plan, frozen authorities, and observed test artifacts.
- [ ] Dispatch a separate security/privacy reviewer covering authority confusion, cross-operator confusion, key purpose, stale/rollback/equivocation/replay/downgrade, parser bounds, credential/origin/subscriber leakage, capture privacy, logging, denial, and fail-open behavior.
- [ ] Reproduce every candidate locally. For each confirmed defect, add and observe a failing regression before the minimal fix, rerun focused and affected suites, and request re-review.
- [ ] Do not proceed to closure until both reports state `READY` with no material blocker.

### Task 10: Fresh validation, one commit, and final Git invariants

**Files:**
- Modify: `evidence/wp8-task10/conformance-result.json` with the final fresh run
- Stage: explicit Task 10 paths only

**Interfaces:**
- Produces: one reviewed commit and a clean local branch; no push.

- [ ] Run `python scripts/verify_wp8_conformance.py` from the repository root and inspect every child result and exact count.
- [ ] Independently rerun commands whose output cannot be safely summarized by the runner, including full Python, complete Cargo test/doc-test, Node/Go verifiers, privacy/secret scan, and `git diff --check`.
- [ ] Confirm all 17 acceptance criteria against observed evidence. If independent wire exchange or packet capture is missing, do not claim Task 10/WP8 closure and stop for human review before committing a misleading closure record.
- [ ] Inspect `git status --short`, `git diff --stat`, and the complete diff. Confirm no frozen vector drift, secrets, temp artifacts, private captures, package-lock changes, unrelated files, or broad generated outputs.
- [ ] Stage each approved Task 10 path explicitly. Inspect `git diff --cached --name-only`, `git diff --cached --stat`, and `git diff --cached --check`.
- [ ] Create exactly one commit: `git commit -m "feat(wp8): complete live federation interoperability"`.
- [ ] Verify commit parent is `7af982239dc8fbc67ae142037f192458c797f4d4`, tree is clean, branch is unchanged, remote still points to Task 9, and no push occurred.

## Plan self-review

- Every behavior-changing task begins with a focused test that fails for the missing behavior before production code is added.
- Python owns Federation authority; Rust consumes only a sealed typed decision; Node and Task 9 Go remain verifier-only.
- The independent peer is isolated from Task 9 Go and Rust and cannot proceed through new semantics.
- Packet capture and independent wire exchange are explicit closure blockers, not documentation-only checkboxes.
- The final claim tier is derived from observed evidence and cannot be upgraded by expected-result metadata.
- The plan preserves the requested one-commit/no-push boundary despite the default workflow's preference for intermediate commits.
