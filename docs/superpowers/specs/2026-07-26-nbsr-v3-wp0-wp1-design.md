# NBSR Vision V3 WP0 and WP1 Design

**Status:** Approved design for implementation planning  
**Date:** 2026-07-26  
**Branch:** `codex/nbsr-v3-wp0-wp1`  
**Scope:** WP0 repository alignment and WP1 Protocol Core v0.1 data model

## Objective

Align the hardened NBSR repository with Protocol Vision V3 and freeze the
deterministic, byte-level Protocol Core v0.1 structures required before a Name
Node or QUIC edge is implemented.

This cycle stops after WP1. It does not implement the NBSR Name Node, QUIC
tunnels, gateway traffic interception, distributed security state, federation,
or production deployment.

## Current baseline

The branch begins at the final hardened Vision V2 prototype. That baseline
contains:

- a registered-name routing demonstration using synthetic addresses,
  Ed25519-signed JWT route capabilities, TLS relaying, and local route policy;
- a separate enterprise demonstration using workload JWTs, OPA, Envoy, and
  short-lived bearer tickets;
- Compose and Kind deployment evidence;
- documentation that currently identifies Vision V2 as authoritative; and
- no canonical CBOR, COSE Sign1, or normative Core v0.1 message implementation.

The existing demonstrations are preserved as implementation evidence. Their
JWT capabilities and tickets do not become Core v0.1 Route Grants and must not
be described as such.

## Design principles

1. Vision V3 becomes authoritative without erasing historical evidence.
2. Documentation distinguishes normative direction, implemented prototype
   behavior, partial behavior, and planned behavior.
3. Protocol Core v0.1 is isolated from applications, deployment systems, and
   operating-system adapters.
4. Wire output is deterministic and testable without public DNS or Internet
   access.
5. Decoding and verification fail closed on malformed, ambiguous, stale,
   unsupported, or cryptographically invalid input.
6. NBSR-enabled client-visible structures and fixtures never contain an origin
   address.
7. Existing enterprise and ISP-profile runtime behavior remains unchanged.

## WP0: repository and documentation alignment

### Document placement and precedence

The supplied
`docs/NBSR_Protocol_Vision_V3_and_Codex_Build_Directive.md` moves to
`docs/architecture/NBSR_Protocol_Vision_V3_and_Codex_Build_Directive.md`.
That file becomes the repository's authoritative architecture and work-program
document.

Vision V2 remains at `docs/architecture/NBSR_Protocol_Vision_v2.pdf`. It is
labeled historical and supporting wherever precedence is described. Existing
security reports and evidence retain their original claims and dates; small
context notices may explain that they evaluated the Vision V2 baseline.

### Protocol documentation

Create:

- `docs/protocol/terminology.md`, containing the canonical V3 terms used by
  code and tests; and
- `docs/protocol/status.md`, mapping V3 requirements and work packages to
  `Implemented`, `Partial`, `Planned`, or `Normative`.

`Normative` means required by Vision V3 or Core v0.1; it does not claim the
behavior is implemented. Each status entry identifies evidence or the explicit
gap.

The existing `docs/vision-v2-conformance.md` remains as historical baseline
evidence and receives a clear supersession notice rather than being rewritten
as V3 evidence.

### README and architecture alignment

Update the README and directly affected architecture/security pages so they
state:

- NBSR is intended to be the configured resolver for legacy and NBSR-enabled
  names;
- legacy results remain DNS-compatible;
- NBSR-enabled names produce route state or a compatibility handle, never an
  origin address;
- the deployable architecture contains isolated Name/Resolution and Secure
  Route/Tunnel planes;
- the source gateway acts for legacy endpoints in the first no-agent lab; and
- the current code is a hardened prototype, not a Core v0.1 implementation or
  production system.

Historical reports are not retroactively rewritten to imply they tested V3.

### Documentation tests

Update `tests/test_documentation.py` to verify:

- required V3 and protocol documents exist;
- Vision V3 is identified as authoritative;
- Vision V2 is retained and labeled historical/supporting;
- the four status terms are defined;
- the README contains the resolver-first and two-plane direction;
- prototype limitations remain explicit; and
- documentation does not claim complete Core v0.1 or V3 conformance.

No existing security evidence or test is removed.

## WP1: Protocol Core v0.1

### Package boundary

Create an isolated `nbsr/protocol/` package. It may depend on the Python
standard library, the selected CBOR implementation, and `cryptography`.
It must not import FastAPI, Pydantic settings, Envoy/OPA adapters, Kubernetes
code, cloud SDKs, or operating-system integration code.

The package contains focused modules for:

- protocol constants and numeric registries;
- canonical CBOR encoding and strict decoding;
- COSE Sign1 Ed25519 operations;
- message schemas and validation;
- lifecycle state types; and
- golden-vector loading used by tests.

Existing JWT code in `nbsr/name_security.py` remains unchanged during WP1.
Runtime migration requires a separate approved plan.

### Version and registries

Core v0.1 defines one explicit protocol version and stable integer registries
for:

- message types;
- signature algorithms;
- critical field identifiers;
- route lifecycle states; and
- the V3 error registry.

Registry values are defined once and imported by schemas, cryptographic
helpers, vectors, and tests. Unknown critical identifiers and unsupported
protocol versions fail closed.

### Canonical CBOR

Encoding uses deterministic CBOR as defined by RFC 8949. The encoder produces
stable bytes for the same typed object. The decoder rejects:

- indefinite-length items;
- duplicate map keys;
- non-minimal integer or length encodings;
- map-key ordering that is not canonical;
- unsupported tags or simple values;
- trailing bytes;
- excessive nesting, collection sizes, or byte/text lengths; and
- values that violate the message schema.

Limits are explicit constants and are exercised at their boundaries. The
implementation must use a CBOR library only if its strict-decoding behavior can
be demonstrated by focused tests. A human decision gate remains for the final
library and cross-language compatibility policy before dependency selection is
committed.

### COSE Sign1 with Ed25519

COSE support is limited to COSE Sign1 with Ed25519/EdDSA for Core v0.1.
Verification:

- accepts only the explicit EdDSA algorithm identifier;
- requires the algorithm in the protected header;
- rejects conflicting, duplicate, unknown critical, or unprotected algorithm
  declarations;
- signs and verifies the canonical payload bytes and external authenticated
  data according to the selected Core v0.1 profile;
- rejects malformed keys and signatures; and
- never chooses an algorithm from untrusted key metadata.

Signing keys and verification keys are separate typed inputs. No generic
"accept any supported algorithm" path is exposed.

### Message schemas

Define immutable typed schemas for:

- Service Record;
- RouteIntent;
- Route Grant;
- revocation entry or statement; and
- protocol error.

The schemas use the exact required fields and numeric keys frozen by the
implementation plan. Across the message set they represent:

- protocol version and message type;
- canonical name and service/transport/port;
- owner and operator identifiers;
- destination edge or opaque route identifier;
- sequence and revocation generation;
- validity interval;
- source-edge and destination-edge binding where applicable;
- proof-of-possession public-key confirmation for Route Grants;
- nonce or replay identifier;
- critical extension identifiers; and
- stable error code with a non-sensitive message.

Route Grants are proof-of-possession-bound authorizations, not reusable bearer
tickets. Origin hostnames and IP addresses are prohibited from all
client-visible Core v0.1 schemas and checked-in vectors.

Validation rejects:

- unknown fields unless the schema explicitly permits a non-critical extension;
- missing or duplicate required fields;
- wrong primitive types, including booleans where integers are required;
- invalid canonical names;
- unsupported transport, service, port, version, or algorithm values;
- invalid validity intervals;
- expired or not-yet-valid messages when temporal validation is requested;
- sequence rollback or stale revocation generation when prior state is
  supplied; and
- ambiguous source/destination or proof-of-possession bindings.

### State types

Define state enums and pure transition validation for the Core v0.1 lifecycle
covered by WP1. The types model creation, admission, active use, draining,
revocation, expiry, failure, and closure without opening sockets or persisting
distributed state.

Illegal transitions fail explicitly. The state model remains independent from
the existing demonstration runtime until a later work package integrates it.

### Golden vectors

Check in deterministic, secret-free valid and invalid vectors under a dedicated
test-vector directory. Each vector includes:

- a stable identifier and purpose;
- the canonical decoded representation;
- expected encoded bytes;
- signature material using published test-only keys when applicable; and
- the expected acceptance or stable failure category.

Invalid vectors cover non-canonical encoding, duplicate keys, malformed
lengths and types, unknown critical fields, signature failure, algorithm
confusion, expiry, future validity, stale sequence, revocation rollback,
proof-of-possession mismatch, and prohibited origin-address content.

No vector contains a production secret, routable origin address, or claim of
network interoperability.

## Testing strategy

Implementation follows test-driven development:

1. Update documentation tests and make WP0 pass without runtime changes.
2. Add failing registry and schema tests.
3. Add strict CBOR rejection tests before encoder/decoder implementation.
4. Add COSE algorithm-confusion and signature-negative tests before signing
   helpers.
5. Add schema, temporal, rollback, and proof-of-possession tests.
6. Add state-transition tests.
7. Add golden-vector byte and failure-category tests.

After focused tests pass, run:

- the complete Python test suite;
- Ruff lint and format checks;
- OPA policy tests; and
- `docker compose config --quiet`.

Live Compose and Kind deployment are not required because WP0/WP1 do not alter
runtime behavior. If dependency or packaging changes affect container builds,
run the narrowest applicable image/build validation and report it separately.

## Error handling and observability

Core validation exposes stable, non-sensitive error categories aligned with
the V3 error registry. Exceptions must not include keys, signatures, tokens,
origin addresses, internal trust paths, or policy details.

WP1 adds no telemetry, network logging, or remote verification. Diagnostic
representations are bounded and safe for deterministic local tests.

## Compatibility and migration

This cycle adds protocol artifacts beside the hardened prototype. It does not:

- replace JWT route capabilities or enterprise bearer tickets;
- change existing API request or response models;
- change synthetic-address allocation;
- alter Compose, Kind, Envoy, OPA, or Windows adapter behavior; or
- declare current runtime traffic Core v0.1 conformant.

A later plan may map the existing registered-name route into the new Service
Record, RouteIntent, and Route Grant types after the protocol structures and
vectors receive independent review.

## Acceptance criteria

WP0 is complete when:

- Vision V3 is authoritative and linked from primary documentation;
- Vision V2 and prior evidence remain accessible and accurately labeled;
- terminology and implementation-status documents exist;
- README and architecture language match the resolver-first, two-plane model;
- all documentation links and focused documentation tests pass; and
- no runtime behavior or existing test coverage is removed.

WP1 is complete when:

- Core v0.1 registry values and immutable schemas are explicit;
- canonical inputs encode to stable bytes;
- strict decoding rejects prohibited CBOR forms and ambiguity;
- COSE Sign1 accepts only the approved Ed25519 profile;
- valid vectors pass and every invalid vector fails with its expected category;
- temporal, rollback, revocation, and proof-of-possession validation fail
  closed;
- origin addresses are absent from client-visible structures and vectors;
- focused and full relevant verification passes; and
- documentation makes no production, interoperability, or complete V3
  conformance claim.

## Human decision gates

Implementation planning must stop for explicit approval before selecting the
final CBOR/COSE dependency and freezing its cross-language compatibility
policy. All other Vision V3 decision gates remain deferred because this cycle
does not implement operator trust, production address allocation, gateway
capture, lifecycle enforcement, distributed replay, federation, logging
retention, a second implementation, or standardization.

