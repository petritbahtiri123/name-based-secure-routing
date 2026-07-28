# NBSR transport profile

**Status:** Proposed profile for human review; not runtime authorization

**Profile name:** `nbsr-quic-1` as already named by Vision V3 and frozen
ServiceRecord data. This document does not register ALPN or allocate wire
values.

## Layering

```text
QUIC v1 connection + TLS 1.3
  = authenticated edge-to-edge Transport Session
      -> independently authorized Service Channel
          -> Application Stream
```

The transport authenticates edges. It does not by itself authorize a service.
The mandatory invariant is session reuse with service isolation.

## QUIC v1 reuse

| QUIC feature | Classification | NBSR treatment |
|---|---|---|
| Connection IDs | Reuse directly | Use QUIC demultiplexing and migration semantics; never treat a Connection ID as Service Identity or authorization |
| Multiplexed streams | Reuse directly | One application stream per proxied TCP flow in the initial profile; stream ownership is bound to a Service Channel |
| Connection-level flow control | Reuse directly, then profile | Bound aggregate memory and bytes; it does not replace per-service quota |
| Stream-level flow control | Reuse directly, then profile | Bound each stream; it does not replace per-channel stream/byte limits |
| Congestion control | Reuse directly | Use the QUIC implementation; NBSR defines no congestion-control algorithm |
| Loss recovery | Reuse directly | Use QUIC recovery; do not add NBSR retransmission |
| Path validation | Reuse directly | A path becomes transport-valid only; all NBSR bindings still apply |
| NAT rebinding | Reuse directly, then profile | May preserve a same-peer Transport Session after path validation |
| Connection migration | Reuse directly, then profile | Same authenticated edge pair only by default; cross-edge movement is NBSR reauthorization/resumption |
| Idle timeout | Reuse directly, then profile | QUIC owns idle detection; configured limits are in the resource profile |
| Graceful close | Reuse directly | Stop new channels/streams, drain eligible work, then use standard close |
| Connection close | Reuse directly | QUIC connection errors end the Transport Session; per-channel errors should not close unrelated services |
| Key update | Reuse directly | QUIC/TLS traffic-key update remains a transport function |
| Retry and address validation | Reuse directly, then profile | Deploy by risk/load policy; a Retry token is not an NBSR grant |
| Anti-amplification | Reuse directly | Preserve QUIC's pre-validation limit; NBSR does not weaken it |

QUIC migration provides transport-path continuity. It does not grant route
continuity. After NAT rebinding or migration, the session and every resumed
channel remain bound to authenticated peer roles, Service Identity, Route
Grant, gateway, client/device, expiry, revocation, replay state, and policy
version or digest. A source IP change alone changes none of those identities.
These checks are the service binding, grant binding, gateway binding, and
policy binding; path validation cannot replace any of them.

## TLS 1.3 profile

- Use TLS 1.3 through QUIC as specified by RFC 9001.
- Require mutual edge authentication between Source Edge and Destination Edge
  with validated, role-appropriate trust anchors. Exact certificate profile
  and federation trust remain gated.
- Bind the application protocol with a dedicated ALPN. The repository uses the
  profile name `nbsr-quic-1`; exact ALPN registration bytes require approval.
- Reuse TLS transcript binding, forward secrecy, certificate validation,
  exporters, and QUIC traffic-key updates.
- Do not implement NBSR cipher suites or a parallel key exchange.

### Service Channel context separation

TLS 1.3 exporters can provide transcript-bound keying material, and RFC 9266
defines a TLS 1.3 channel-binding construction. NBSR can reuse the exporter
primitive with a dedicated label and canonical context inputs that include at
least the transport-session identity, service identity/name digest, channel
identity, authorized peer roles, and grant or policy binding.

The exact label, input encoding, output length, directionality, rekey behavior,
and test vectors are not frozen. They require cryptographic review. The generic
RFC 9266 `tls-exporter` channel-binding value is not itself a secret key and
must not be reused as a Service Channel traffic key.

## Streams and control

- One bidirectional control stream carries bounded Core control envelopes.
- The initial TCP profile uses one reliable QUIC application stream per
  proxied TCP connection.
- Opening an application stream requires an active, independently authorized
  Service Channel.
- Stream reset is contained to the stream. Channel revocation rejects new
  streams and closes or drains affected streams according to approved policy.
- A channel-level failure must not unnecessarily terminate unrelated channels
  on the same Transport Session.
- HTTP CONNECT may be reused in a future HTTP proxy deployment profile, but
  it does not replace the NBSR control protocol or RouteGrant semantics.

No new control message, stream preface, state, or transition is approved here.

## Future UDP and IP profiles

For UDP, prefer CONNECT-UDP with HTTP Datagrams/Capsule Protocol, or a narrowly
specified QUIC DATAGRAM mapping, rather than custom datagram framing. QUIC
DATAGRAM is connection-scoped and has no stream ID, so an approved profile
must bind a datagram flow identifier to exactly one Service Channel.

For IP proxying, evaluate CONNECT-IP and Capsule Protocol. An IP profile must
not create one universal VPN-like authorization context. Exact UDP and IP
framing are separate human gates and are not part of WP3.

## Migration, resumption, and handover

- Same-edge NAT rebinding/path migration may reuse QUIC path validation.
- Same-edge TLS resumption can reduce handshake cost only after checking
  current NBSR expiry, revocation, replay, gateway, service, device/client, and
  policy bindings.
- Cross-edge resume is not QUIC connection migration. It requires explicit
  NBSR reauthorization and remains gated.
- Gateway handover cannot transfer a grant or Service Channel blindly.
- Replayed resume or handover proof fails closed.

## 0-RTT

There is no 0-RTT for route-changing control messages. Route open/accept,
grant use that allocates new route state, renew, revoke, origin update,
migration, resume, handover, or policy-changing messages must wait for 1-RTT
keys and completed peer authentication. A future replay-safe allowlist would
require explicit approval and conformance tests.

## MTU and packet sizing

Reuse QUIC packet sizing and DPLPMTUD. Do not create a custom PMTU algorithm.
The profile must:

- support QUIC's required 1200-byte Initial datagram behavior;
- subtract QUIC, TLS, NBSR, and any proxy/capsule overhead from the usable
  inner payload;
- use the peer's negotiated QUIC DATAGRAM size for any future datagram profile;
- reject or segment at the correct existing layer rather than silently
  fragmenting a QUIC DATAGRAM;
- define client-safe errors that do not expose Origin Endpoints; and
- separately specify TCP stream, UDP datagram, and future IP packet behavior.

Future IP-tunnel fragmentation and ICMP behavior remain part of the IP-profile
approval gate.

## Admission order

No expensive route or channel state is allocated until:

1. cheap packet and framing validation succeeds;
2. QUIC address validation is satisfied where required;
3. bounded Core deterministic-CBOR structural validation succeeds;
4. replay, generation, and sequence checks succeed;
5. required signatures are verified, using bounded safe caching;
6. policy evaluation authorizes the service and route; and
7. route and Service Channel capacity is reserved.

## Open approvals

Approval is required for the QUIC library, exact ALPN, edge certificate/trust
profile, transport reuse key, application-stream binding bytes, exact exporter
derivation, timeout/resource defaults, cross-edge resume, UDP framing, IP
framing, and any new wire element.
