# NBSR implementation status

**Baseline date:** 2026-07-26  
**Authority:** [Protocol Vision V3](../architecture/NBSR_Protocol_Vision_V3_and_Codex_Build_Directive.md)  
**Evidence baseline:** hardened Build Week snapshot reporting 180 passed, 1
skipped, Ruff clean, five OPA tests passed, Compose validation, live enterprise
and ISP-profile demonstrations, and Kind isolation probes on 2026-07-25.

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
| V3 resolver-first architecture | Normative | The Name Node resolves both legacy and NBSR names; current code is not yet that universal resolver |
| DNS-compatible legacy resolution through NBSR | Partial | A loopback DNS adapter and deterministic gateway resolution exist; full UDP/TCP Name Node, recursion/forwarding parity, authoritative serving, and DNSSEC behavior are WP2 |
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
| Route Grant Core v0.1 structure | Planned | WP1 |
| Deterministic CBOR and COSE Sign1 | Planned | WP1; current enterprise and ISP slices use JSON/JWT |
| Explicit Ed25519 algorithm allowlist | Partial | Existing JWT paths use explicit EdDSA allowlists; COSE profile does not exist |
| `nbsr-quic-1` inter-edge tunnel | Planned | WP3; current relay uses TLS 1.3 over TCP |
| Independent source and destination admission | Planned | WP3 |
| Outbound origin connector | Planned | Protected prototype origins exist, but the V3 connector state machine does not |
| Opaque HTTP/HTTPS forwarding | Implemented | ISP vertical slice relays TCP bytes and preserves end-to-end application TLS |
| Multiplexed streams, renewal, drain, and key update | Planned | WP4 |
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

WP0 aligns documentation and preserves evidence without changing code behavior.
WP1 freezes protocol data structures, numeric registries, deterministic bytes,
COSE Sign1 Ed25519 behavior, state types, and valid/invalid vectors. WP2 and
later work MUST NOT begin without separate approval.
