# NBSR implementation status

**Baseline date:** 2026-07-30

**Authority:** [NBSR Protocol Vision V3.6](../architecture/NBSR_Protocol_Vision_V3.6.md)
**Evidence baseline:** the final hardened-branch report records 255 passed and
1 skipped on supported Python 3.12 and 3.13, Ruff clean, five OPA tests passed,
Compose validation, live enterprise and ISP-profile demonstrations, and Kind
isolation probes. The WP0 merge was rechecked on 2026-07-26 with 261 passed and
1 skipped, tracked Python files Ruff-clean, and Compose configuration valid.
That local recheck used out-of-range Python 3.14 because no supported
interpreter was installed; the available OPA launcher could not execute, so
the earlier five-test OPA evidence was not refreshed.

The current branch was revalidated on 2026-07-30 with 680 passed and 1 skipped,
Ruff check and format clean across tracked Python source/tests/scripts,
`pip check` clean, Core v0.2 vectors reproduced exactly, and all Rust
format/Clippy checks clean. The isolated Rust transport crate passed 8
configuration tests and 11 handshake tests. The Core v0.1 COSE Sign1 profile
passed 36 focused COSE tests. The deterministic Core v0.1 package contains 34
Core v0.1 vectors—6 valid and 28 invalid—and regenerates byte-for-byte. Core
v0.1 now also has deterministic bounded property coverage across all six
models, arbitrary CBOR bytes, malformed lengths, schema critical extensions,
and byte mutations of every signed object segment. Python
3.14 remains outside the supported interpreter range, so this is development
evidence rather than a release certification.

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
| DNS-compatible legacy reachability through NBSR | Partial | A loopback DNS adapter and deterministic gateway resolution exist; full Name Node behavior and temporary DNS-backed OriginSet conversion are WP2 |
| NBSR name request without origin IP in client state | Implemented | Name-route responses and synthetic mappings omit the origin address |
| Signed NBSR Service Record | Planned | WP1 freezes the schema and signature vectors; WP2 adds a signed local registry |
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
| `nbsr-quic-1` inter-edge tunnel | Partial | An isolated Quinn 0.11.11/rustls 0.23.43 loopback handshake boundary now proves TLS 1.3 mTLS, exact ALPN, and bounded failure; no tunnel runtime or streams exist |
| Independent source and destination admission | Partial | The isolated handshake verifies exact Source/Destination Edge certificate SANs; RouteGrant, policy, Service Channel, and runtime admission remain WP3 work |
| Outbound origin connector | Planned | Protected prototype origins exist, but the V3 connector state machine does not |
| Opaque HTTP/HTTPS forwarding | Implemented | ISP vertical slice relays TCP bytes and preserves end-to-end application TLS |
| Explicit Transport Session and single Service Channel binding | Planned | The handshake crate deliberately exposes no stream API and allocates no Route Context or Service Channel |
| Reusable multi-service Transport Session with isolated Service Channels | Planned | WP4; wire representation and key schedule require approval |
| Internal Derived OriginSet | Implemented | Immutable, wire-neutral model with bounded endpoints, generation/sequence rollback protection, same-sequence equivocation rejection, and deterministic tests |
| Legacy DNS-backed internal OriginSet | Implemented | Isolated bounded legacy DNS adapter builds Derived OriginSet values, preserves stable synthetic mapping inputs, separates DNS TTL from authorization, and supports the approved last-known-good policy; NameRelay integration remains gated |
| Signed NBSR-native OriginSet publication | Planned | Core v0.2 or approved extension decision required |
| Multiplexed streams, renewal, origin drain, and key update | Planned | WP4 |
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
- QUIC, arbitrary UDP, live mobility, or transparent failover;
- distributed replay or revocation guarantees;
- origin concealment against a compromised destination operator or host
  administrator.

## Next approved boundary

WP0 documentation alignment, WP1 Tasks 1-7, the wire-neutral Derived OriginSet
model, the bounded legacy DNS adapter, the Core v0.2 deterministic vector
package, and the isolated Rust QUIC/TLS handshake spike are complete at their
documented prototype scope.

The next boundary is the Phase E single-service path. The handshake evidence
does not authorize it: WP3 runtime remains gated. Before implementation, a
separate reviewed design and TDD plan must define the minimum Transport
Session-to-Service Channel binding, RouteGrant admission, control framing,
validated OriginSet selection, application-stream lifecycle, origin
concealment, and exact abort criteria. No new Core v0.1 key, message code,
error code, state, transition, extension, or COSE wrapper may be introduced.
