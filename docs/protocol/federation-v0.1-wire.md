# NBSR Federation v0.1 implemented wire profile

This reference summarizes the frozen Development Profile implemented by the
repository. Normative object schemas, registries, deterministic vectors, and
human decisions remain authoritative over this summary.

Federation objects use deterministic CBOR and the approved COSE Sign1 or
bilateral-signature profiles. Operator IDs are 32-byte genesis commitments;
their text form is lowercase Bech32m with HRP `nbsr`. Ownership, delegation,
trust bundles, checkpoints, proofs, revocation, lifecycle state, key purpose,
generation, sequence, dependency state, and error precedence are validated
from authenticated bytes. Descriptive or expected-result metadata supplies no
authority.

For federated route establishment, `ROUTE_OPEN.body_version = 2` contains the
closed key-8 `federation_binding` map `[1, 1, 1,
"nbsr-federation-dev-v1", route_grant_digest,
federation_context_digest]` under numeric keys 0 through 5. The body has exactly
keys 0 through 8. Non-federated body version 1 remains unchanged and forbids key
8. No automatic fallback is permitted.

F75 signs the approved deterministic-CBOR 16-item
`NBSR-FED-ROUTE-OPEN` transcript. It retains Core session, request, channel,
route, destination edge, nonce, transport, service, port, RouteGrant, and time
bindings and adds exact Core/body/Federation/profile versions plus the digest of
the exact carried signed RouteGrant bytes and authenticated bilateral
Federation context. Destination admission independently validates all bindings
before channel activation or application payload forwarding.

`VerifiedFederationAuthorization` is an internal sealed typed value, not a wire
object. It cannot replace remote F75 proof. The existing `nbsr/1` TLS/QUIC
Transport Session, Route Context, Service Channel exporter binding, and
Application Stream state remain authoritative.

Failures for malformed/non-canonical input, invalid authority or purpose,
stale/revoked state, rollback, equivocation, replay, mismatch, downgrade, or
unsupported versions are fail-closed. No new Core message code, exporter, key
schedule, generic extension framework, or non-federated behavior is defined.
