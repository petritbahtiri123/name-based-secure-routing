# NBSR implementation status

**Baseline date:** 2026-07-31

**Authority:** [NBSR Protocol Vision V3.6](../architecture/NBSR_Protocol_Vision_V3.6.md)
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
| Partition-safe replay and revocation | Planned | WP6; current replay cache is bounded but process-local |

## Operations, federation, and conformance

| Capability | Status | Evidence or gap |
|---|---|---|
| One installable package with isolated planes | Planned | WP5 |
| Clean no-agent client behind an upgraded gateway | Partial | Windows adapter proves the boundary; router/enterprise/ISP packaging remains |
| Reversible route/firewall ownership journal | Partial | Windows synthetic IPv6 ownership journal exists; full Linux/OpenWrt packaging remains |
| Multi-zone HA and shared security state | Planned | WP6 |
| Two-operator ISP lab | Planned | WP7 |
| Signed ownership, delegation, transparency, and global federation | Planned | WP8 |
| Independent second-language implementation | Planned | WP8 |
| Independent Core v0.2 vector verification | Implemented | Dependency-free Node.js verifier independently validates the 32-artifact deterministic package; this is conformance evidence, not a second runtime |
| Public conformance suite and Internet-Draft | Planned | WP8 |

## Current non-claims

The repository MUST NOT claim any of the following:

- production readiness;
- full Protocol Core v0.1 conformance;
- global federation;
- anonymity from source or destination operators;
- DDoS elimination;
- system-wide arbitrary UDP, live mobility, or transparent failover;
- distributed replay or revocation guarantees;
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
