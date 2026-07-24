# Security model

The control plane authenticates signed workload JWTs and delegates every route
decision to OPA. It alone holds the routing-ticket private key. The verifier
holds only its public key and binds authorization to the request Envoy actually
received. Envoy exposes a fixed payments route; clients cannot select upstreams.
The control-plane API and Envoy gateway require server-authenticated TLS using
the dedicated enterprise demo CA. The verifier uses the actual HTTP method and
path in Envoy's ext-authz subrequest, not client-supplied metadata headers.
Envoy adds and overwrites the fixed service identity only inside that
subrequest, and the verifier rejects missing or duplicate service metadata.
Envoy's administrative listener is bound to container loopback.

The design fails closed when identity validation, OPA, verifier, or ticket
validation fails. Sensitive credentials are not intentionally logged. Local
demo keys are ignored by Git and written atomically with owner-restricted
permissions on POSIX or restricted DACLs on Windows. Docker's build context
excludes Git metadata, secrets, tokens, caches, logs, and generated artifacts.
Replay detection for the enterprise bearer-ticket path, rotation automation,
distributed rate limiting, durable audit logs, and production PKI are outside
prototype scope.

## ISP name-routing profile

The name-route control boundary signs short-lived route bindings with a key
separate from identity and enterprise routing-ticket keys. A deployed name
control service receives the name-binding private key plus only its ISP TLS
server key; the enterprise control plane receives neither. A
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

Relay destination policy is applied to each literal returned by resolution
immediately before a socket is opened. Global unicast is allowed by default;
loopback, private, link-local, multicast, reserved, unspecified, IPv4-mapped
private, and otherwise non-global addresses are denied unless the hostname and
address match an explicit trusted-origin rule. This second check is required
even after earlier name validation so DNS rebinding cannot exchange a permitted
answer for a forbidden one. A route capability maps to one canonical TCP port:
`http` to 80 and `https` to 443.

The replay cache, synthetic allocator, and per-client admission registry have
explicit capacity and expiry bounds. Name-route requests are limited per
client and globally before synthetic allocation. These controls reduce
single-process memory and CPU exhaustion; they are not a distributed ISP
abuse-control system.

The Kubernetes reference manifest starts with default-deny ingress and egress.
Each workload then receives only its named peers and ports. DNS egress is
limited to the workloads that resolve service names and to port 53 in
`kube-system`; no namespace-wide arbitrary egress rule remains. Kind uses a
digest-pinned node image whose bundled network-policy implementation is tested
with both allowed and denied live connections.

The first release uses a loopback adapter to prove the Windows protocol path.
It is not a signed Windows Filtering Platform driver and does not claim
production-ready traffic interception. HTTP/3/QUIC, arbitrary UDP, raw IP
tunneling, public-DNS fallback, durable distributed state, and production key
rotation are excluded. Configured name traffic fails closed when the binding,
proof, route, private resolution, or upstream connection is invalid or
unavailable.
