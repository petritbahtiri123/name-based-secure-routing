# NBSR Federation v0.1 Development Profile — public draft 00

This document describes implemented development-profile behavior. It is not an
IETF standard and makes no claim of standards-body adoption.

The key words MUST, MUST NOT, SHOULD, SHOULD NOT, and MAY describe conformance
requirements for this repository profile.

## Terminology

An Operator is an independent administrative domain. A Service ID binds a
canonical name to its genesis owner. Federation authority is authenticated
ownership, delegation, trust, transparency, lifecycle, revocation, and policy
state. A Transport Session carries Route Contexts; each Route Context may bind
Service Channels and admitted Application Streams.

## Architecture

Source and destination operators MUST retain separate identities, signing keys,
transport identities, trust roots, policy, audit, rate-limit, and admission
state. Source admission MUST precede independent destination admission. Payload
MUST NOT be forwarded before all required route, channel, and stream gates pass.

## Operator ID

The binary Operator ID MUST be the frozen 32-byte SHA-256 genesis commitment.
Text presentation MUST be lowercase Bech32m with HRP `nbsr`. Wrong case, HRP,
checksum, discriminator, padding, or length MUST fail.

## Ownership and delegation

Ownership and delegation MUST be established from authenticated canonical
objects and exact signer authority. Delegation scope MUST bind the name,
Service ID, actors, service class, transport, port/capability, validity, and
dependencies. A source cannot mint destination authority and a destination
cannot mint owner authority.

## Trust bundles and transparency

Trust bundles, checkpoints, inclusion/consistency proofs, and witness evidence
MUST satisfy the frozen thresholds and transition rules. Missing, partial,
stale, malicious, or conflicting evidence MUST fail closed.

## Key purposes and lifecycle

Keys MUST be used only for their approved purpose. `kid`, Operator ID,
generation, sequence, activation, expiry, revocation, recovery, and terminal
state MUST be validated. Safe rotation MAY activate a new key or bundle only
after authenticated transition checks; revoked or stale predecessors MUST fail.

## Rollback, equivocation, and split view

Lower or conflicting generations/sequences, rollback, equivocation, and split
view evidence MUST be handled according to frozen precedence and enforcement.
Terminal state MUST NOT resurrect.

## Deterministic encoding

Wire objects and transcripts MUST use the repository deterministic-CBOR profile.
Duplicate keys, non-preferred integers, indefinite forms, unknown closed-map
keys, malformed types, excessive nesting, and over-limit values MUST fail.
Security decisions MUST NOT depend on JSON, debug fields, oracle labels, or a
decoded/re-encoded approximation of signed bytes.

## Transport and F75 route establishment

Non-federated `ROUTE_OPEN.body_version = 1` remains unchanged and forbids key 8.
Federated routes MUST use body version 2 with exactly keys 0 through 8. Key 8
MUST contain the frozen six-field federation binding version 1.

The F75 proof MUST sign the deterministic 16-item `NBSR-FED-ROUTE-OPEN`
transcript. `route_grant_digest` MUST be SHA-256 of the exact carried signed
RouteGrant bytes. `federation_context_digest` MUST identify the fully
authenticated bilateral context accepted by both admissions. Version,
identity, route, destination, nonce, transport, service, port, digest, or time
substitution MUST invalidate the proof. Federated admission MUST NOT fall back
to the legacy transcript.

The internal Rust `VerifiedFederationAuthorization` is non-wire and MUST NOT be
treated as remote proof. Inter-edge transport uses the existing mutually
authenticated encrypted `nbsr/1` QUIC/TLS profile and existing Service Channel
exporter. No new exporter or key schedule is defined.

## Error behavior

Invalid signature, purpose, authority, state, profile, binding, replay,
downgrade, unsupported value, or malformed input MUST reject before application
delivery. Existing frozen precedence determines the externally selected error.

## Privacy considerations

Clients route by name or synthetic mapping and MUST NOT receive real Origin
Endpoint addresses. Successful client-visible resolution, route state, normal
logs, and public captures MUST exclude protected origins. Federation does not
provide anonymity. Ciphertext alone cannot prove authorization correctness.

## Operational and security considerations

Operators SHOULD isolate key purposes and administrative domains, retain replay
and terminal-state evidence, audit bounded failures, rotate through authenticated
transitions, and protect capture/key material. Production custody, HSMs,
governance, monitoring, DDoS controls, and deployment engineering are outside
this development evidence.

## Conformance requirements

Conforming implementations MUST validate the closed manifests and frozen valid
and invalid vectors without oracle metadata. They MUST agree on canonical bytes,
signatures, authority decisions, precedence, lifecycle, rollback, and
equivocation behavior. The public runner MUST return non-zero on a divergence
and MUST identify unsupported evidence as a skip rather than a pass.

## Extension and versioning rules

Unknown critical behavior MUST fail closed. This draft defines no generic
extension framework. New message codes, fields, profiles, transcript layouts,
serializations, capabilities, exporters, or authority require a separate
approved registry and wire decision. Version downgrade MUST NOT occur
automatically.

## Implementation evidence

Python is the reference Federation authority. Node and Go independently verify
the frozen Federation artifacts. Rust consumes a sealed typed authorization and
exercises the live same-Rust Quinn route/channel/stream path. A public-safe
packet capture exists. Independent route/stream wire interoperability remains
not proven because no second wire-capable implementation is present.

## Future work and non-claims

Future work includes a genuinely independent wire peer, production custody and
operations, deployment studies, and separate latency/performance evaluation.
The evidence is not production readiness, not Internet-scale deployment, and
not vendor or ISP adoption; it is not an IETF standard. It also does not prove global
governance, anonymity, DDoS elimination, or production SLAs.
