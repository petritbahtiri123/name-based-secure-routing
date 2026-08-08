# WP8 Task 10B Independent Route/Stream Wire Interoperability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prove genuine cross-implementation NBSR route/stream interoperability between the frozen Rust/Quinn destination peer and an independently implemented Go/quic-go source peer without changing protocol authority.

**Architecture:** A standalone Go module under `interop/nbsr-go-peer/` uses pinned `github.com/quic-go/quic-go@v0.61.0` only for QUIC v1/TLS 1.3 machinery. It independently implements deterministic CBOR, Core v0.2 envelopes, COSE/RouteGrant validation, F75 ROUTE_OPEN v2, correlation/state transitions, exporter-bound channel admission, stream admission, and payload gating from frozen documents and vectors; it imports neither `verifiers/federation-go`, the repository Python NBSR implementation, nor Rust code. A Rust test endpoint exposes the existing `nbsr-transport` destination role over a cross-process loopback boundary, while the repository-level pytest harness owns process orchestration and evidence comparison.

**Tech Stack:** Go 1.26.5; `github.com/quic-go/quic-go@v0.61.0` (MIT, exact module checksum); Go standard library for TLS, X.509, SHA-256, and Ed25519; Rust 2024; Quinn 0.11.11; rustls 0.23.43; deterministic CBOR; COSE Sign1/Ed25519; pytest orchestration.

## Global Constraints

- Starting checkpoint is exactly `695b583de447ce166f4d051c16550c073874ad1d` on `codex/nbsr-v3-wp0-wp1`.
- The frozen ALPN is exactly `nbsr-quic-1`; `nbsr/1` is not an alternate ALPN.
- Preserve all Core v0.2, F75 ROUTE_OPEN v2, Federation v0.1, RouteGrant, exporter, registry, capability, fallback, and deterministic-CBOR authority byte-for-byte.
- Allocate no message code, field, transcript item, object, registry value, capability, fallback, or serialization rule.
- The independent package must not import, execute, wrap, FFI-call, shell out to, or proxy protocol decisions through `crates/nbsr-transport`.
- `quic-go` supplies only QUIC/TLS machinery. Every NBSR parser, encoder, verifier, state transition, correlation rule, and payload gate is independently implemented.
- Task 9 Go verifier code must not be copied, imported, invoked, or treated as an authority oracle.
- Package metadata is not feasibility evidence: Task 1 requires an executed disposable Go/quic-go to Rust/Quinn ALPN, mTLS, stream-ID, 0-RTT, and cross-stack exporter-parity proof before the dependency gate can become GREEN.
- The rejected aioquic investigation remains recorded: aioquic 1.3.0 had no supported public exporter API and must not be forked, patched, or accessed through private TLS state.
- The Rust interoperability server may expose only configuration, readiness, and public test authority. It must not precompute or disclose NBSR decisions, expected messages, F75 transcripts, exporter outputs, acceptance labels, or oracle data.
- Expected-result labels and oracle metadata never establish authority or select outcomes.
- All behavior changes follow literal RED, observed expected failure, minimal GREEN, focused verification, and review.
- If a frozen specification ambiguity or contradiction is found, stop before changing either peer and request human authority.
- Do not start performance benchmarking, deployment, demos, video work, or unrelated protocol features.
- Do not push without separate human approval.

---

## File structure

| Path | Responsibility |
|---|---|
| `interop/nbsr-go-peer/go.mod` | Isolated Go module and exact quic-go pin |
| `interop/nbsr-go-peer/go.sum` | Go module checksums for the closed dependency graph |
| `interop/nbsr-go-peer/DEPENDENCIES.md` | Version, license, module checksum, dependency, CVE/audit, rejected-aioquic, and API-feasibility evidence |
| `interop/nbsr-go-peer/feasibility-result.json` | Executed Go/quic-go to Rust/Quinn exporter parity and negative-handshake evidence |
| `interop/nbsr-go-peer/internal/cbor/cbor.go` | Strict bounded deterministic-CBOR codec |
| `interop/nbsr-go-peer/internal/core/core.go` | Independent Core v0.2 envelope/body schemas and framing |
| `interop/nbsr-go-peer/internal/authority/authority.go` | COSE Sign1, RouteGrant, Ed25519, digests, and F75 transcript verification |
| `interop/nbsr-go-peer/internal/state/state.go` | Independent HELLO/route/channel/stream correlation and replay state |
| `interop/nbsr-go-peer/internal/transport/quic.go` | quic-go adapter, exact ALPN/mTLS identity, control stream, exporter, and application streams |
| `interop/nbsr-go-peer/cmd/nbsr-go-peer/main.go` | Bounded source-peer process entrypoint and machine-readable result |
| `interop/nbsr-go-peer/internal/**_test.go` | Independent unit/vector/mutation tests that never import repository implementations |
| `crates/nbsr-transport/src/bin/wp8_interop_server.rs` | Existing Rust destination runtime exposed as a deterministic loopback test process |
| `tests/federation/test_independent_wire_peer.py` | Cross-process positive/negative interoperability and isolation gate |
| `evidence/wp8-task10b/independent-wire-result.json` | Exact implementations, direction, messages, versions, payload digest, and negative outcomes |
| `scripts/verify_wp8_task10b.py` | Task 10B manifest-first validation entrypoint |

### Task 1: Dependency, license, and platform feasibility gate

**Files:**
- Create: `interop/nbsr-go-peer/go.mod`
- Create: `interop/nbsr-go-peer/go.sum`
- Create: `interop/nbsr-go-peer/DEPENDENCIES.md`
- Create: `interop/nbsr-go-peer/feasibility-result.json`
- Create: `tests/federation/test_independent_peer_dependency_boundary.py`

**Interfaces:**
- Consumes: Go 1.26.5 host, frozen ALPN `nbsr-quic-1`, Rust TLS/exporter requirements.
- Produces: an isolated reproducible environment and a go/no-go result before NBSR peer code exists.

- [ ] Write a failing repository test requiring the isolated Go module, exact `github.com/quic-go/quic-go v0.61.0` pin and checksum, MIT license record, complete direct/transitive inventory, Go 1.26.5 compatibility, no local `replace`, and no dependency on `verifiers/federation-go`, repository Python NBSR, or Rust.
- [ ] Run `python -m pytest tests/federation/test_independent_peer_dependency_boundary.py -q` and observe failure because the isolated dependency package is absent.
- [ ] In a disposable module outside the repository, execute Go/quic-go `v0.61.0` against Rust/Quinn `0.11.11` and prove QUIC v1, TLS 1.3, exact ALPN, mTLS, bidirectional stream ID 0, disabled 0-RTT, no key logging, and the public `ConnectionState().TLS.ExportKeyingMaterial` path.
- [ ] Require both stacks to derive the exact frozen 32-byte WP4 exporter independently from label `EXPORTER-NBSR-Service-Channel-v2` and the exact canonical context bytes; compare only post-derivation SHA-256 digests and require byte parity.
- [ ] Execute unsupported-ALPN, wrong identity, wrong CA, missing client certificate, wrong label, and changed-context negatives; require fail-closed or separated output.
- [ ] Record quic-go `v0.61.0`, module checksum `h1:ui88A53s8MSVYLC56en0KQ17HARk+9986Dn0SBfKNvA=`, MIT license, Go compatibility, direct/transitive graph, public-API scan, `go mod verify`, `go test`, `go vet`, and pinned `govulncheck` result in `DEPENDENCIES.md`.
- [ ] Record the failed aioquic 1.3.0 exporter investigation honestly without creating a Python peer or retaining aioquic as a project dependency.
- [ ] Stop for human review if exporter parity, mTLS identity, ALPN, stream-ID, or 0-RTT cannot be reproduced without private/internal APIs, patches, or changed frozen behavior.
- [ ] Run the dependency-boundary test and repository dependency/privacy scanner; require PASS before Task 2.

### Task 2: RED cross-process claim gate and isolation proof

**Files:**
- Create: `tests/federation/test_independent_wire_peer.py`
- Create: `interop/nbsr-go-peer/cmd/nbsr-go-peer/main.go`

**Interfaces:**
- Consumes: the isolated environment from Task 1.
- Produces: `run_peer(config_path: Path) -> dict[str, object]` CLI behavior and a failing end-to-end claim gate.

- [ ] Write a cross-process pytest that launches the Rust destination executable, launches the independently built Go source peer with `--config <path>`, and expects `CLIENT_HELLO`, `EDGE_HELLO`, `ROUTE_OPEN`, `ROUTE_ACCEPT`, `STREAM_OPEN`, `STREAM_ACCEPT`, and the fixed payload digest in the result.
- [ ] Add an isolation test that scans imports/process invocations and rejects `verifiers/federation-go`, repository Python NBSR, Rust library paths, `cargo`, cgo/FFI, subprocess protocol delegation, and expected-result/oracle fields inside the independent package.
- [ ] Run the two tests and observe the expected failures because the CLI reports `independent peer not implemented` and the Rust endpoint is absent.
- [ ] Implement only Go argument parsing, strict closed configuration loading, bounded JSON result output, and the explicit not-implemented exit; do not add protocol behavior in this task.
- [ ] Rerun and retain the end-to-end RED while making the CLI/isolation unit checks GREEN.

### Task 3: Independent deterministic CBOR and Core framing

**Files:**
- Create: `interop/nbsr-go-peer/internal/cbor/cbor.go`
- Create: `interop/nbsr-go-peer/internal/cbor/cbor_test.go`
- Create: `interop/nbsr-go-peer/internal/core/core.go`
- Create: `interop/nbsr-go-peer/internal/core/core_test.go`

**Interfaces:**
- Produces: `encode(value) -> bytes`, `decode_exact(wire, limits) -> object`, `encode_envelope(envelope) -> bytes`, `decode_envelope(wire) -> Envelope`, and QUIC-varint control-frame functions.

- [ ] Add literal tests against frozen Core v0.2 valid envelope/body bytes for all six required messages and independent re-encoding equality.
- [ ] Add RED mutations for duplicate/unknown/missing keys, non-shortest integers/lengths, indefinite items, tags, floats, invalid UTF-8, excessive depth/collection/byte length, trailing data, oversized frame length, and invalid QUIC varint framing.
- [ ] Run the independent unit suite and observe failure because the codec/modules do not exist.
- [ ] Implement the smallest standalone deterministic codec and closed numeric-key schemas without importing repository codecs or generators.
- [ ] Rerun until all positive bytes match exactly and every malformed/mutation case fails closed.

### Task 4: Independent RouteGrant and F75 cryptographic authority

**Files:**
- Create: `interop/nbsr-go-peer/internal/authority/authority.go`
- Create: `interop/nbsr-go-peer/internal/authority/route_grant_test.go`
- Create: `interop/nbsr-go-peer/internal/authority/f75_test.go`

**Interfaces:**
- Produces: `verify_route_grant(exact_cose, trust, opened_at) -> VerifiedRouteGrant`, `f75_transcript(context) -> bytes`, and `sign_f75(context, session_private_key) -> bytes`.

- [ ] Add RED tests consuming exact frozen RouteGrant/F75 artifacts without reading manifest expected outcomes.
- [ ] Require exact SHA-256 over carried immutable RouteGrant COSE bytes, exact authenticated Federation context digest, the approved 16-item transcript, and Python/Node/Rust byte parity.
- [ ] Add one-field mutations for Core/body/binding/extension/profile versions, session/request/channel/route IDs, destination edge, nonce, transport, service, port, RouteGrant bytes/digest, opened_at, context digest, signature, authority expiry, revocation, and transcript substitution.
- [ ] Implement strict COSE Sign1/Ed25519 verification, authority checks, F75 encoding/signing, and typed verified results independently.
- [ ] Rerun until valid authority passes and every mutation fails with a stable local reason category.

### Task 5: Independent peer state and correlation machine

**Files:**
- Create: `interop/nbsr-go-peer/internal/state/state.go`
- Create: `interop/nbsr-go-peer/internal/state/state_test.go`

**Interfaces:**
- Produces: `SourcePeerState` transitions `NEW -> HELLO_SENT -> HELLO_ACCEPTED -> ROUTE_SENT -> ROUTE_ACCEPTED -> STREAM_SENT -> STREAM_ACCEPTED -> PAYLOAD_ALLOWED`.

- [ ] Add RED transition tests for the exact positive sequence and rejection of payload at every earlier state.
- [ ] Add wrong session/request/channel/stream/service/transport/port, stale sequence, replay, duplicate accept, response-before-request, ROUTE_OPEN v1/v2 downgrade, unsupported profile/version, and terminal-state resurrection cases.
- [ ] Implement the minimal monotonic state machine with bounded replay sets and typed immutable accepted context.
- [ ] Rerun the state suite and require all invalid transitions to leave payload permission false.

### Task 6: Exact QUIC/TLS and exporter adapter

**Files:**
- Create: `interop/nbsr-go-peer/internal/transport/quic.go`
- Create: `interop/nbsr-go-peer/internal/transport/quic_test.go`
- Create: `crates/nbsr-transport/src/bin/wp8_interop_server.rs`

**Interfaces:**
- Consumes: exact test CA/certificates, `nbsr-quic-1`, Core frames, and `SourcePeerState`.
- Produces: a quic-go source connection and existing Rust destination process over loopback.

- [ ] Add RED tests for exact ALPN, mutual identity validation, QUIC v1, TLS 1.3, disabled 0-RTT, first bidirectional control stream, application stream ID correlation, control-frame bounds, and frozen exporter output.
- [ ] Implement the Rust test endpoint as orchestration around public `nbsr-transport` APIs only; it emits a ready record containing port and public test authority paths, never protocol decisions for the independent peer.
- [ ] Add an oracle-boundary test that rejects any Rust readiness/configuration field containing expected NBSR messages, encoded envelopes, F75 transcript/signature bytes, exporter values, acceptance labels, or protocol decisions.
- [ ] Implement the quic-go adapter through public APIs only, with key logging disabled and no HTTP/3 layer.
- [ ] Add negative tests for wrong peer certificate/SAN/CA, unsupported ALPN, early data, exporter mismatch, unexpected stream ordering, and oversized frames.
- [ ] Rerun Rust endpoint tests and isolated Go adapter tests before combining state and wire exchange.

### Task 7: Positive frozen route/channel/stream exchange

**Files:**
- Modify: `interop/nbsr-go-peer/cmd/nbsr-go-peer/main.go`
- Modify: `tests/federation/test_independent_wire_peer.py`
- Create: `evidence/wp8-task10b/independent-wire-result.json`

**Interfaces:**
- Produces Go-source to Rust-destination exchange and payload digest evidence.

- [ ] Extend the RED cross-process test to require actual ordered exchange of `CLIENT_HELLO`, `EDGE_HELLO`, `ROUTE_OPEN` body version 2, `ROUTE_ACCEPT`, `STREAM_OPEN`, and `STREAM_ACCEPT`.
- [ ] Require Core version 2, binding tuple `[1, 1, 1, "nbsr-federation-dev-v1"]`, exact RouteGrant/context digests, exact request/session/channel/stream correlation, and payload transmission only in `PAYLOAD_ALLOWED`.
- [ ] Implement source message construction, response verification, exporter/channel confirmation, application-stream opening, fixed safe payload transfer, and returned SHA-256 digest in the independent Go peer.
- [ ] Run the cross-process test and compare the received payload digest to the locally computed fixture digest.
- [ ] Write evidence containing language/runtime/library versions, exact direction, message list, versions/profile, payload literal digest, result, dependency lock digest, and an isolation statement; never include keys or plaintext packet capture.

### Task 8: Required live negative interoperability matrix

**Files:**
- Modify: `tests/federation/test_independent_wire_peer.py`
- Modify: `evidence/wp8-task10b/independent-wire-result.json`

**Interfaces:**
- Produces one independently executed fail-closed result for every mandatory negative.

- [ ] Parameterize cross-process mutations for wrong peer identity, ALPN, Core/body/Federation/profile version, malformed/non-canonical/over-limit CBOR, session/request/channel/stream ID, service, transport, port, RouteGrant digest, Federation context digest, proof signature, expired/revoked authority, replay, v1/v2 downgrade, transcript substitution, and payload before route/channel/stream acceptance.
- [ ] Ensure each mutation changes authenticated input or live state rather than expected labels.
- [ ] Run every mutation separately and require no application payload bytes at the destination.
- [ ] Record exact observed rejection stage/reason and zero accepted payload for every case.
- [ ] Add relabeling/oracle-mutation isolation tests proving evidence labels cannot change peer decisions.

### Task 9: Task 10B conformance, capture, and documentation

**Files:**
- Create: `scripts/verify_wp8_task10b.py`
- Modify: `scripts/verify_wp8_conformance.py`
- Create: `docs/protocol/wp8-task10b-independent-wire-evidence.md`
- Modify only after proof: `docs/protocol/status.md`
- Modify only after proof: `docs/protocol/wp8-federation-v0.1-decision.md`
- Modify only after proof: `docs/internet-drafts/draft-nbsr-federation-00.md`

**Interfaces:**
- Produces reproducible cross-implementation validation and accurate claim-tier updates.

- [ ] Add RED runner tests requiring Go module checksum verification, isolated unit tests, Rust endpoint tests, positive/negative cross-process tests, implementation-isolation checks, artifact drift, secret/privacy scan, and explicit failure propagation.
- [ ] Implement the manifest-first runner and integrate it into the full WP8 matrix without removing existing gates.
- [ ] Capture the independent flow only with the already-approved Npcap loopback/BPF/privacy procedure; use a distinct Task 10B artifact and validate every packet before publication.
- [ ] Update documentation to `independent route/stream wire interoperability: PROVEN` only after the live positive and complete negative matrix pass.
- [ ] Preserve non-claims for production readiness, Internet scale, performance, adoption, governance, deployment, and standard status.

### Task 10: Independent reviews, final validation, and closure proposal

**Files:**
- Create: `evidence/wp8-task10b/correctness-review.md`
- Create: `evidence/wp8-task10b/security-privacy-review.md`
- Create: `evidence/wp8-task10b/conformance-result.json`

**Interfaces:**
- Produces two `READY` dispositions and a human-reviewable WP8 closure proposal.

- [ ] Dispatch independent correctness/interoperability review over checkpoint `695b583..working-tree`, frozen authority, both implementations, vectors, wire evidence, and claim accuracy.
- [ ] Dispatch separate security/privacy review over dependency risk, peer isolation, authority confusion, parser bounds, stale/replay/downgrade, payload gating, credential/origin/subscriber leakage, logs, capture, and fail-open behavior.
- [ ] Reproduce each confirmed finding RED-first, apply the minimum fix, and rerun both reviews until each returns `READY`.
- [ ] Run the complete Task 1-10B matrix including full Python, Node, Go, Rust, original Core lock, F75 overlay, all generators, both live paths, independent negative matrix, dependency audit, privacy scan, documentation, artifact drift, and `git diff --check`.
- [ ] Report exact pass/fail/skip counts and explain every skip; no independent-wire skip is permitted for WP8 closure.
- [ ] Verify no frozen artifact or dependency outside the approved isolated peer package changed.
- [ ] Stop with a closure proposal for human approval; do not commit or push unless separately authorized.

## Plan self-review

- Every behavior-changing task begins with a focused RED and explicit expected failure.
- The independent peer has no Rust or repository-Python protocol dependency.
- quic-go is limited to QUIC/TLS machinery and is pinned/audited before peer code.
- The exact frozen ALPN is `nbsr-quic-1` everywhere.
- Every required positive message and negative case maps to an explicit task.
- Protocol ambiguity stops both implementations rather than creating matching invented behavior.
- Documentation cannot upgrade the claim until live cross-process evidence and both reviews pass.
