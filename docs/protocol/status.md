# NBSR implementation status

**WP8 Task 0:** Proposed for human approval.
**WP8-NORMATIVE-SOURCE-01: CLOSED.** The exact digest-matching historical source
is repository-accessible and provenance-locked. Task 1 may begin after human
approval. Repository-contained decisions,
Development Profile allocations, baseline locking, and verifier ownership are
planning artifacts only. No federation runtime is implemented by Task 0; no
Federation wire freeze or live-federation evidence is claimed.

The pending correction proposal uses the canonical 11-state Operator lifecycle,
three recovery stages, and a semantics-derived Federation message registry;
none is implemented runtime evidence.

**Baseline date:** 2026-08-07

**Authority:** [NBSR Protocol Vision V3.6](../architecture/NBSR_Protocol_Vision_V3.6.md)

**WP8 schema gate:** `WP8-SCHEMA-REQUIREDNESS-01` has a focused Schema
Decision Supplement at `CLOSED` by human approval of commit
`a0bb467b0f533886930745f855deadbd3d5904f7`. The approved proposal
now controls the exact Development Profile schema decisions it freezes and
authorized Task 2 only at closure. A later explicit human approval authorizes
Task 3 against the same unchanged supplement and Task 2 baseline; Core remains
unaltered.

**WP8 Task 2:** Operator ID, `OperatorRegistryRecord`,
`KeyAuthorizationRecord`, and the uniquely determined root-authorized tagged
COSE Sign1 boundary are implemented. Registrar+witness and recovery-threshold
signature-set transport packaging remains unresolved and is not invented.

**WP8 Task 3:** `NameOwnershipRecord`, the closed eleven-dimension
`DelegationScope`, `DelegationRecord`, Task 2 key-authority reuse, and iterative
bounded ownership/delegation-chain verification are implemented at deterministic
Development Profile scope. Verification enforces exact name/Service ID ancestry,
scope narrowing, parent-bounded validity, depth/chain/graph/traversal limits,
lineage, revocation, terminal state, transfer, and explicitly permitted recovery.
This is payload and semantic validation evidence only: no registrar+witness or
recovery-threshold signature-set container has been invented, and no Task 4
trust-bundle, transparency, or witness runtime is implemented.
Typed transition bindings are trusted outputs from independently validated
transfer/recovery semantics; they are not evidence that the unresolved
multi-signature container has been authenticated.
Fresh Task 3 closure evidence on 2026-08-07: 44 Task 3 tests, 123 Task 2-3
tests, 213 Federation tests, and the full Python suite (`1293 passed, 1
skipped`) passed. The 28 schema literals, schema and registry render checks,
Core baseline lock, Core v0.1/v0.2 vectors, generic Node verifier, dedicated
WP4 exporter verifier, Ruff check and format, `pip check`, and `git diff
--check` also passed.
Fresh Task 2 closure evidence on 2026-08-07: 169 Federation tests and the full
Python suite (`1249 passed, 1 skipped`) passed; the 28 literal schema fixtures,
schema renderer, 110-artifact Core v0.2 baseline lock, Core v0.1/v0.2 vector
checks, generic Node verifier, dedicated WP4 exporter verifier, Ruff check and
format, `pip check`, and `git diff --check` also passed.
**Evidence baseline:** the final hardened-branch report records 255 passed and
1 skipped on supported Python 3.12 and 3.13, Ruff clean, five OPA tests passed,
Compose validation, live enterprise and ISP-profile demonstrations, and Kind
isolation probes. The WP0 merge was rechecked on 2026-07-26 with 261 passed and
1 skipped, tracked Python files Ruff-clean, and Compose configuration valid.
That local recheck used out-of-range Python 3.14 because no supported
interpreter was installed; the available OPA launcher could not execute, so
the earlier five-test OPA evidence was not refreshed.

The current branch was revalidated on 2026-07-30 with 815 passed and 1 skipped,
including 207 focused WP2A tests and 167 frozen
registry/schema/state/vector/CBOR/COSE tests. Ruff check and format, `pip
check`, both vector regeneration checks, and Compose configuration passed.
The local Docker configuration produced an access warning, and OPA could not
be refreshed because no executable `opa` command was present. The isolated
Rust transport evidence remains 8 configuration tests and 11 handshake tests.
The Core v0.1 COSE Sign1 profile retains 36 focused COSE tests. Its 34 Core
v0.1 vectors—6 valid and 28 invalid—regenerate byte-for-byte, and bounded
property coverage remains in place across all six models, CBOR, schema
extensions, and signed-object mutation. Python 3.14 is now inside the declared
development range; this remains prototype evidence rather than release
certification.

The WP3 continuation was freshly revalidated on 2026-07-31 with 817 passed and
1 skipped across the full Python suite, 70 focused WP3/frozen-protocol tests,
and 32 passing Rust tests. Rust formatting and Clippy, Python Ruff check and
format, `pip check`, both vector regeneration checks, and `git diff --check`
passed. This evidence remains limited to the origin-free single-service lab
boundary documented below.

WP4 is complete at its documented origin-free reusable multi-service same-edge loopback lab scope.
Pre-documentation implementation baseline: 114 executable Rust tests and 16 doctests (130 total),
332 focused WP4/frozen-protocol Python tests, and 826 passed and 1 skipped in the
full Python suite. Rustfmt, Clippy with `-D warnings`, Ruff check and format
(`107 files already formatted`), `pip check`, both Core regeneration checks,
and `git diff --check` passed. The separately owned Core v0.2 exporter subtree
passed Python and Node verification for 2 valid and 21 invalid/mutation cases.
Final independent review reported 0 Critical, 0 Important, and 0 Minor findings
after the original Critical and Important findings were fixed with regression tests.
Post-documentation current validation: the same 114 executable Rust tests and
16 doctests (130 total), 335 focused tests, 829 passed and 1 skipped (830 collected)
in the full Python suite, and Ruff reported 108 files already formatted;
Rustfmt, Clippy, `pip check`, both Core generators, WP4 Python and
Node vector verification, and `git diff --check` also passed.

WP5 is complete at deterministic planning and simulated policy-conformance scope.
Fresh 2026-08-01 validation recorded 71 focused WP5 tests, 903 passed and 1 skipped
in the full Python suite, and 114 executable Rust tests and 16 doctests
(130 total). Ruff check passed; Ruff format reported 125 files already
formatted; `pip check`, Core v0.1/Core v0.2 regeneration, WP4 exporter Python
and Node verification (2 valid and 21 invalid/mutation cases), Compose
configuration, OPA 5/5, Rustfmt, Clippy with `-D warnings`, and `git diff
--check` passed. The finalized external scan covered 8/8 changed source/config
files for `7d3a59a..fb3e302`, closed five candidates, and reported zero
findings. The fresh closure review fixed two additional defects—journal-read
TOCTOU and forged rollback-plan profile binding—with zero remaining findings.
This is prototype/lab evidence only: no live nftables validation, no live
policy-routing validation, no OpenWrt validation, no clean no-agent client
demonstration, no operational rollback execution, no privileged installer
evidence, and no production-readiness claim.

WP6 is complete and evidence-closed at bounded deterministic prototype scope.
The implementation is a deterministic storage-neutral state machine, private
snapshot repository, and simulated multi-replica quorum model. Fresh
2026-08-01 validation recorded 65 focused WP6 tests and 971 passed and 1
skipped in the full Python suite. Ruff check passed and Ruff format reported
132 files already formatted; dependency checks, Core v0.1/Core v0.2
regeneration, WP4 exporter Python/Node verification, the independent WP6
snapshot verifier, Rustfmt, Clippy, Docker Compose configuration, OPA 5/5, and
`git diff --check` passed. Cargo ran 114 executable tests and 16 doctests (130
total). Independent security and correctness closure reviews report zero
remaining confirmed findings.

WP6 evidence is simulated multi-replica behavior only. It proves bounded
canonical snapshots, monotonic retained state, stale/replay/rollback/
equivocation rejection, fail-closed quorum reads, 5-second failover, 30-second
drain, and non-resurrection inside the approved prototype boundary. It is not
live consensus, live HA, or crash-recovery evidence.

WP7 is complete and evidence-closed at deterministic two-operator lab scope.
The implementation is a single-threaded, in-process model with source-first
admission, independent source and destination authority, pair-wide bounded
quota/replay/audit state, deterministic fair-share eviction, and one confined
destination connector. The documentation-inclusive focused suite contains 109
focused WP7 tests. Independent correctness and security closure reviews report
zero remaining confirmed findings.

Fresh 2026-08-02 validation recorded 1,080 passed and 1 skipped in the full
Python suite. Ruff check passed and Ruff format reported 140 files already
formatted; `pip check`, Core v0.1/Core v0.2 regeneration, WP4 exporter Python
and Node verification (2 valid and 21 invalid/mutation cases), the independent
WP6 snapshot verifier, byte-identical double WP7 verification, Rustfmt, Clippy
with `-D warnings`, Docker Compose configuration, OPA 5/5, bounded privacy and
artifact scans, and `git diff --check` passed. Cargo ran 114 executable tests
and 16 doctests (130 total).

WP7 evidence proves the 5-second source admission, 5-second destination
admission, 30-second drain, fail-closed overload and authority decisions,
operator-owned audits, exact registered connector capabilities, canonical
topology verification, and safe raw-scan behavior only inside the approved
simulated model. The connector performs no network I/O and its receipt is not
derived from the Origin Endpoint. This is not live deployment, federation,
anonymity, or production evidence.

This file separates evidence from intent. `Implemented` means verified behavior
exists at prototype scale. It does not imply Core v0.1 conformance, production
readiness, global federation, or independent interoperability.

## Status meanings

| Status | Meaning |
|---|---|
| Implemented | Verified behavior exists in the hardened prototype at its documented scale |
| Partial | A vertical slice exists, but one or more mandatory V3 properties are missing |
| Planned | No credible implementation exists yet; an approved work package defines the intended work |
| Normative | V3 requires the behavior for the relevant future conformance claim |

## Architecture and name plane

| Capability | Status | Evidence or gap |
|---|---|---|
| V3.6 universal synthetic resolver architecture | Normative | Every successful upgraded-network resolution returns a Synthetic IP; current code is not yet that universal resolver |
| DNS-compatible legacy reachability through NBSR | Partial | A loopback DNS adapter and bounded DNS-backed OriginSet conversion exist; the approved WP2A plan adds the signed, synthetic-only Name Node core |
| NBSR name request without origin IP in client state | Implemented | Name-route responses and synthetic mappings omit the origin address |
| Signed NBSR Service Record | Implemented | WP2A adds a bounded owner-bound local registry; no federation or production trust distribution |
| WP2A Name Node core | Implemented | Signed registry, bounded resolution state, synthetic-only core, privacy-safe observability, and loopback UDP/TCP DNS are verified at lab scope |
| Real recursive DNS, production DNSSEC, and Web PKI validation | Planned | WP2A accepts only injected normalized discovery data and makes no production resolver or certificate-validation claim |
| Resolution Context ID | Partial | Local adapter/session correlation exists, but subscriber/CPE/DoH/DoT context contracts are not defined |
| Synthetic-handle allocation | Implemented | Bounded IPv4/IPv6 prototype pools, expiry, collision controls, and ownership journaling exist |
| Shared source-edge address mode | Planned | Requires a trustworthy name signal and is not the primary WP2 path |
| Native `connect(name)` API | Planned | Later compatibility optimization; not required for the first no-agent lab |

## Route security and data plane

| Capability | Status | Evidence or gap |
|---|---|---|
| Ed25519-bound name route | Implemented | Prototype binding covers hostname, handles, gateway, ports, expiry, route ID, and session-key thumbprint |
| Proof-of-possession admission | Implemented | Ephemeral Ed25519 client session signs the relay admission context |
| Core v0.1 immutable D6 models and schemas | Implemented | WP1 Tasks 1-4 freeze registries, states, deterministic CBOR, and the six D6 model/schema mappings; not integrated into runtime |
| Deterministic CBOR | Implemented | Bounded RFC 8949 scanner/encoder and focused tests; no network integration |
| COSE Sign1 | Implemented | WP1 Task 5 provides exact tag-18, protected `alg=-8`/opaque `kid`, attached-payload Ed25519 signing and caller-context verification; it is not integrated into runtime |
| Explicit Ed25519 algorithm allowlist | Implemented | The Core v0.1 COSE boundary accepts only typed Ed25519 keys and rejects algorithm confusion; existing prototype JWT paths remain separate |
| Core v0.1 deterministic vectors | Implemented | WP1 Task 6 freezes a hash-bound package of 6 valid and 28 invalid vectors covering objects, deterministic CBOR, schemas, COSE, bindings, time/sequence state, and documentation-only IP rejection |
| Core v0.1 bounded property coverage | Implemented | WP1 Task 7 runs 300 deterministic Hypothesis examples per property across model round trips, arbitrary bytes, signed-object mutations, malformed lengths, and critical-extension rejection |
| [Core v0.1 wire contract](core-v0.1-wire.md) | Implemented | WP1 Task 8 publishes the reviewed cross-language contract and stable `nbsr.protocol` API; this is a protocol data boundary, not runtime integration or independent interoperability evidence |
| `nbsr-quic-1` inter-edge tunnel | Partial | The isolated Quinn 0.11.11/rustls 0.23.43 loopback boundary proves TLS 1.3 mTLS, exact ALPN, bounded Core v0.2 control framing, and no Core v1 fallback; it is not a production tunnel or origin connector |
| Independent source and destination admission | Partial | At the WP3 origin-free lab boundary, the authenticated Quinn peer SAN is bound through CLIENT_HELLO/EDGE_HELLO to the policy identities before caller-trusted signed RouteGrant admission. Production trust operation and origin-segment admission remain unimplemented. |
| Outbound origin connector | Planned | Protected prototype origins exist, but the V3 connector state machine does not |
| Opaque HTTP/HTTPS forwarding | Implemented | ISP vertical slice relays TCP bytes and preserves end-to-end application TLS |
| Explicit Transport Session and single Service Channel binding | Implemented | WP3 completes the Rust-only origin-free lab slice: authenticated HELLO/ROUTE sequencing, signed admission, correlated ROUTE_ACCEPT, one admitted channel, and one actual Quinn stream. It has no OriginSet selection, origin connection, relay integration, multi-service reuse, or production claim. |
| Reusable multi-service Transport Session with isolated Service Channels | Implemented | WP4 proves compatible-session reuse with independently authorized TCP/UDP Service Channels, exporter binding, bounded lifecycle, quotas, audit, drain, failure containment, and same-edge resume at origin-free loopback lab scope. |
| Internal Derived OriginSet | Implemented | Immutable, wire-neutral model with bounded endpoints, generation/sequence rollback protection, same-sequence equivocation rejection, and deterministic tests |
| Legacy DNS-backed internal OriginSet | Implemented | Isolated bounded legacy DNS adapter builds Derived OriginSet values, preserves stable synthetic mapping inputs, separates DNS TTL from authorization, and supports the approved last-known-good policy; NameRelay integration remains gated |
| Signed NBSR-native OriginSet publication | Planned | Core v0.2 or approved extension decision required |
| Multiplexed streams | Implemented | WP4 lab scope: 64 independently gated streams per channel and 2,049 peer-initiated bidirectional streams per Transport Session including control; no production claim |
| Renewal, origin drain, and key update | Planned | WP5+ |
| Partition-safe replay and revocation | Partial | WP6 deterministically simulates replicated replay/revocation continuity and fail-closed disagreement; no live partition or consensus evidence |

## Operations, federation, and conformance

| Capability | Status | Evidence or gap |
|---|---|---|
| Deterministic Linux/OpenWrt gateway planning | Implemented | WP5 emits bounded declarative dual-stack capture, reject, policy-route, DNS, health, journal, verification, and rollback intent without live mutation |
| One installable package with isolated planes | Partial | WP5 provides the dependency-free planner/CLI and simulated conformance model; no privileged installer or live platform package evidence |
| Clean no-agent client behind an upgraded gateway | Partial | Windows adapter proves the boundary; router/enterprise/ISP packaging remains |
| Reversible route/firewall ownership journal | Implemented | WP5 records bounded applied operation IDs and exact prior resolver state, then emits trusted-profile-bound reverse-order rollback intent; operational rollback remains unverified |
| Multi-zone HA and shared security state | Partial | WP6 provides a storage-neutral state machine and deterministic quorum simulation; no live multi-zone HA |
| Two-operator ISP lab | Implemented | WP7 deterministic single-threaded, in-process admission, abuse, audit, connector-confinement, and topology simulation; no live ISP or federation evidence |
| Signed ownership, delegation, transparency, and global federation | Partial | WP8 Tasks 2-3 implement operator/key authority, ownership, closed scope algebra, bounded delegation chains, and exact-purpose single-Sign1 verification at deterministic Development Profile scope; threshold packaging, Task 4 transparency/witness runtime, live federation, and global federation are not implemented |
| Independent second-language implementation | Planned | WP8 selects a clean-room Go implementation after schema/vector freeze; the current Node verifier remains independent byte/object evidence, not a runtime |
| Independent Core v0.2 vector verification | Implemented | Dependency-free Node.js verifier independently validates the 32-artifact deterministic package; this is conformance evidence, not a second runtime |
| Public conformance suite and Internet-Draft | Planned | The WP8 plan defines vector, interoperability, evidence, and working-draft gates; none is implemented or standards-approved yet |

## Current non-claims

The repository MUST NOT claim any of the following:

- production readiness;
- full Protocol Core v0.1 conformance;
- global federation;
- anonymity from source or destination operators;
- DDoS elimination;
- system-wide arbitrary UDP, live mobility, or transparent failover;
- distributed replay or revocation guarantees;
- live etcd, live Raft, live PostgreSQL, or live multi-host consensus;
- production HA, crash/reboot durability, or complete partition tolerance;
- cross-edge handover or cross-edge resumption authority;
- OriginSet publication interoperability or a new wire protocol;
- origin concealment against a compromised destination operator or host
  administrator.

## Next approved boundary

WP0 documentation alignment, WP1 Tasks 1-8, the wire-neutral Derived OriginSet
model, the bounded legacy DNS adapter, the Core v0.2 deterministic vector
package, the isolated Rust QUIC/TLS handshake spike, and
[WP2A](wp2a-name-node-core.md) are complete at their documented prototype
scope.

WP3 is complete at its documented origin-free single-service loopback lab
scope. The freshly verified 2026-07-31 Rust slice has 32 passing tests. The
authenticated Quinn peer SAN is bound to CLIENT_HELLO and EDGE_HELLO; decoded
RouteOpen plus a caller-trusted signed RouteGrant feed bounded Destination
admission after session/request sequence, session-key thumbprint, edge nonce,
RouteOpen proof, service, transport, port, policy, expiry, replay, and capacity
checks. A correlated ROUTE_ACCEPT is required before the admitted channel can
create its StreamGate. That exact channel admits one Service Channel and one
TCP Application Stream through the real loopback QUIC application-stream
lifecycle. Payload before STREAM_ACCEPT is reset without delivery; an accepted
payload is echoed only in memory up to the 4 KiB bound, and an oversized
payload is reset without echo. The Origin Endpoint remains internal and is not
connected. Core v0.2 failure never retries as Core v0.1. Multi-service
Transport Session reuse remains WP4. NameRelay remains unchanged. This is no
production readiness claim.

The boundary has no OriginSet selection, no origin connection, no relay
integration, no multi-service reuse, and no production-readiness claim.

WP4 supersedes only the WP3 single-service restriction. It proves the exact
reuse key `(source_edge_id, destination_edge_id, trust_profile_id, ALPN,
protocol_version)`, a fresh RouteGrant and fresh nonces per channel, canonical
CBOR TLS-exporter binding with a single SHA-256 context hash, and isolated TCP
and native QUIC DATAGRAM channels. Exact lab limits are 32 channels per
session, 64 streams per channel, a 2,049-stream session transport cap including
control, 1 MiB per stream, durable bidirectional 8 MiB per channel, 1,200-byte
UDP application payloads in a 1,235-byte frame, queue 64, 100 datagrams/second
with burst 100, one 1,024-event audit queue shared across channels within a
Transport Session, a 3,600-second session maximum,
30-second drain, and same-edge resume for at most 30 seconds capped by grant
and old-session hard authority.

WP4 retains no OriginSet selection, no Origin Endpoint connection or forwarding,
no NameRelay integration, no production-readiness claim, no cross-edge resume,
no 0-RTT, no WP5+ behavior, and no frozen Core v0.1
registry, schema, state, or wrapper change.

No real recursive DNS, production DNSSEC/Web PKI policy, relay integration,
validated OriginSet selection, native OriginSet publication, new Core v0.1
registry allocation, multi-service reuse, or production-readiness claim is
authorized by this slice.

WP5 adds deterministic gateway planning and simulated policy conformance only.
Any live nftables, policy-routing, OpenWrt,
privileged-installer, operational-rollback, or clean no-agent exercise requires
a separate human-approved validation gate.

WP6 adds deterministic replicated origin and continuity state only. It reuses
existing wire-neutral OriginSet and approved WP4 authority as safe digests and
metadata; it allocates no wire semantics and mints no handover or resume proof.
No live etcd, no live Raft, no live PostgreSQL, no live multi-host consensus,
no production HA, no crash/reboot durability, no cross-edge handover, no
cross-edge resumption, no OriginSet publication interoperability, no new wire
protocol, no complete partition tolerance, no global federation, and no
production-readiness claim are made.

WP7 adds a deterministic two-operator simulation only. It allocates no wire
semantics, and caller-verified local authority cannot mint, sign, distribute,
rotate, or persist WP3-WP6 authority. WP7 makes no production readiness, no
live two-ISP deployment, no independent real administration, no real
subscriber enforcement, no DDoS mitigation or elimination, no origin
anonymity, no global federation, no signed ownership or delegation, no
transparency, no trust distribution or rotation, no new wire protocol, no
OriginSet publication interoperability, no cross-edge handover or resumption,
no live consensus, no complete partition tolerance, no independent
interoperability, and no raw-scan resistance outside the exact simulated
topology claims. It also provides no process-global runtime uniqueness,
distributed replay protection, persistence, concurrency safety, crash
durability, distributed transaction, or live resource scheduler.
