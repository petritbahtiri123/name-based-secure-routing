# Transport Session and Service Channel architecture

**Status:** Approved V3.6 architecture; wire representation and key schedule
pending human approval

**Runtime status:** Not implemented

## Required hierarchy

`Transport Session -> Route Context / Service Channel -> Application Stream`

### Transport Session

An authenticated and encrypted edge-to-edge transport relationship between a
specific Source Edge and Destination Edge under a compatible trust profile,
protocol version, policy basis, and path. The planned implementation expects
QUIC/TLS 1.3, but this document does not approve an exact wire profile.

The session authenticates the edge relationship. It does not authorize every
service reachable through either edge.

### Route Context

Bounded authorization and lifecycle state for one Service Identity. It binds
the canonical Service Name or digest, service identifier, Route Grant,
client/device or subscriber context, Source Edge, Destination Edge, allowed
transport/port, lease, policy digest, replay state, and revocation state.

### Service Channel

The independently authorized, name-bound, and service-bound logical security
context that carries one Route Context through a Transport Session. A Service
Channel is independently revocable, has independent quotas, and has explicit
audit attribution.

### Application Stream

One proxied application flow carried within one Service Channel. The first
profile treats one TCP connection as one Application Stream. Application
protocol state remains owned by the application.

## Session reuse, service isolation

An authenticated Transport Session may carry Service Channels for multiple
services only when peer identities, trust profile, protocol version, path,
policy, and capacity permit reuse.

Reuse must preserve:

- independently authorized admission for every Service Channel;
- name-bound and service-bound Route Context;
- independently revocable channel state;
- independent quotas and noisy-neighbor controls;
- per-service audit attribution without origin disclosure;
- failure containment so a rejected, reset, expired, or revoked channel does
  not unnecessarily terminate unrelated channels; and
- an independent cryptographic or transcript-bound context for every channel.

A grant for service A cannot authorize service B. Reusing edge authentication
does not reuse Route Grants, admission results, policy decisions, nonces,
leases, or revocation decisions unless a future approved profile explicitly
and safely defines a bounded shared artifact.

## Rejected extremes

V3.6 rejects:

1. one universal VPN-like authorization context for all traffic; and
2. one full edge-to-edge cryptographic handshake for every hostname or
   Application Stream.

The intended balance is authenticated transport reuse with service-level
authorization and security isolation.

## Cryptographic separation

Every accepted Service Channel must have an independent cryptographic or
transcript-bound security context derived from or bound to the authenticated
Transport Session.

At minimum, the eventual context must bind:

- Transport Session identity;
- channel identifier;
- route identifier;
- Service Identity/name digest;
- Route Grant or authorization digest;
- Source Edge and Destination Edge;
- client/device or subscriber binding;
- policy version/digest; and
- protocol/profile version.

No exact HKDF, exporter label, context encoding, key lifetime, or rekey formula
is frozen. That algorithm and its wire/test representation are a human decision
gate.

## Authorization and lifecycle

For each new Service Channel:

1. resolve the synthetic mapping to a RouteIntent;
2. authenticate and validate service-specific authorization;
3. bind the channel to the current route, policy, lease, replay, and revocation
   state;
4. derive or bind the independent channel security context;
5. enforce channel quotas before opening streams; and
6. attribute audit events to the opaque route/channel and authorized service.

Revoking service A denies its new streams and applies its approved completion
policy. It must not revive after migration or resumption. Service B may
continue on the same Transport Session unless the session itself, a shared
edge identity, or an explicit session-wide policy is invalid.

## Failure containment

| Failure | Required containment |
|---|---|
| Channel admission rejected | Other channels remain usable |
| Channel quota exhausted | Only that channel is throttled or denied unless a documented fair-share limit applies |
| Channel cryptographic check fails | That channel fails closed; investigate session compromise without granting cross-service access |
| Service revoked | That Service Channel follows revoke/drain policy; unrelated services are not implicitly revoked |
| Transport Session fails | All carried channels lose transport, but none gains authorization during recovery |
| Destination Edge compromised | Revoke or isolate affected edge/session/channel authority; owner identity and other services are not implicitly transferable |

## Mobility, resumption, and handover

Same-edge QUIC path migration may preserve transport only after path validation.
Cross-edge recovery creates a new authenticated edge relationship or uses an
explicitly approved handover. No Route Context or Service Channel transfers
blindly.

Restored state must still satisfy expiry, revocation, replay, gateway,
client/device, service, and policy bindings. Replayed resume proof, stale
handover authority, and revoked-channel resurrection fail closed.

## Audit and privacy

Audit must distinguish Transport Session, Route Context, Service Channel, and
Application Stream. Shared transport cannot collapse per-service accounting.
Default records use opaque identifiers, result codes, counters, policy digest,
and generation. They do not expose origin addresses, payloads, keys, proofs, or
a reconstructable client-to-origin map.

## Version boundary

This architecture does not change the frozen 17 message codes, 19 error codes,
D6 field schemas, or state registries. Service-channel wire representation,
transport reuse key, grant reuse policy, key derivation, and any new message or
state allocation require explicit human approval.
