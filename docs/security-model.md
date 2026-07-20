# Security model

The control plane authenticates signed workload JWTs and delegates every route
decision to OPA. It alone holds the routing-ticket private key. The verifier
holds only its public key and binds authorization to the request Envoy actually
received. Envoy exposes a fixed payments route; clients cannot select upstreams.

The design fails closed when identity validation, OPA, verifier, or ticket
validation fails. Sensitive credentials are not intentionally logged. Local
demo keys are ignored by Git. Replay detection, rotation automation, rate
limiting, durable audit logs, and production PKI are outside prototype scope.

## ISP name-routing profile

The name-route control boundary signs short-lived route bindings with a key
separate from identity and enterprise routing-ticket keys. A deployed name
control service receives the name-binding private key plus only its ISP TLS
server key; the legacy enterprise HTTP control plane receives neither. A
deployed name relay receives only the name-binding public key plus its distinct
ISP TLS server key. Clients receive and trust only the separate ISP demo CA.
The ISP CA and both server certificates are separate from the optional
enterprise demo CA and every JWT/signing key. The relay verifies hostname,
synthetic address, gateway, allowed TCP port, expiry, client proof-of-possession,
and relay-nonce replay before it privately resolves and opens the origin.
Client-visible route state contains synthetic compatibility addresses, never
the resolved destination address.

The ISP name-control API and relay transport require server-authenticated TLS.
The relay then forwards opaque HTTP and HTTPS application bytes inside that
transport. It does not terminate application TLS, substitute application
certificates, inspect content, or require subscriber identity. The gateway
operator nevertheless sees each requested name and its
resolved destination because the gateway performs resolution and routing;
NBSR does not provide anonymity from that operator.

The first release uses a loopback adapter to prove the Windows protocol path.
It is not a signed Windows Filtering Platform driver and does not claim
production-ready traffic interception. HTTP/3/QUIC, arbitrary UDP, raw IP
tunneling, public-DNS fallback, durable distributed state, and production key
rotation are excluded. Configured name traffic fails closed when the binding,
proof, route, private resolution, or upstream connection is invalid or
unavailable.
