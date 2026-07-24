# NBSR Security Hardening Design

## Status and scope

This specification closes the validated security findings from the July 2026
NBSR deep-security review without changing the product into a user-identity,
billing, or traffic-inspection system. It hardens both existing profiles:

- the public ISP name-routing profile, where NBSR privately resolves a requested
  service name and relays opaque HTTP/HTTPS bytes; and
- the enterprise demonstration, where Envoy, OPA, identity JWTs, and
  method/path-scoped route tickets protect internal services.

The work applies to the isolated `codex/nbsr-security-hardening` branch. The
Build Week `main` branch is outside the change scope. Full NBSR Protocol Vision
v2 conformance is not claimed: this remains a Windows-first HTTP/HTTPS
prototype with Docker Compose and Kubernetes deployment examples.

## Security invariants

The hardened implementation must enforce these invariants:

1. A client-facing control or gateway endpoint never sends a bearer credential,
   route ticket, service request, or relay admission over plaintext.
2. A caller cannot supply enterprise authorization metadata that Envoy or the
   verifier treats as trusted request context.
3. The public name relay never connects to a loopback, link-local, private,
   multicast, unspecified, reserved, metadata, or otherwise non-global address
   unless the normalized hostname and address match an explicit trusted-origin
   rule.
4. Destination policy is evaluated on every resolved literal immediately
   before connection, so a public-to-private DNS rebind fails closed.
5. Generated private keys, tokens, and ownership journals are written
   atomically and are readable only by the current principal and required
   operating-system administrators.
6. Synthetic address allocation and relay replay protection have explicit
   capacities and do not perform a complete historical scan on every request.
7. A route capability authorizes only its corresponding transport port.
8. Kubernetes network policy grants each workload only the destinations and
   ports it needs; a deployment preflight confirms that the selected cluster
   enforces policy.

## Selected architecture

### Explicit transport and header guards

Bootstrap creates separate server certificates for the enterprise control plane
and gateway, in addition to the existing ISP name-control and name-relay
certificates. Compose and Kind mount those certificates read-only. Client
defaults, health checks, demo scripts, and deployment examples use HTTPS with
the generated CA. The Windows relay API no longer accepts a configuration
without a CA path; TLS construction errors stop startup or connection attempts.

The first release uses server-authenticated TLS for the public ISP profile.
Client mTLS remains an optional enterprise integration and is not introduced as
a mandatory ISP identity mechanism.

At the enterprise gateway, Envoy removes every inbound `x-nbsr-*` metadata
header before it derives method, path, and service from the actual downstream
request. Derived headers use explicit overwrite semantics. The authorization
verifier rejects missing, repeated, or ambiguous trusted metadata rather than
falling back to defaults. Envoy's administrative listener binds to loopback and
is not published to the client network.

### Relay destination policy

`PrivateResolver` returns validated address literals, not arbitrary resolver
output. The default rule accepts globally routable unicast addresses only.
Explicit trusted-origin rules are exact hostname-to-network mappings used for
operator-controlled private services such as the local `facebook.test` demo.
Rules never allow all RFC1918 space, all loopback space, or a hostname wildcard.

The relay applies the rule to every `getaddrinfo` result immediately before
`asyncio.open_connection`. If any candidate is denied it is skipped; if no
candidate remains, admission fails with a stable relay error and no socket is
opened. The rule is re-run for each connection rather than cached with the
binding, which closes DNS rebinding and time-of-check/time-of-use gaps.

Kubernetes policy is split by workload:

- name-control can receive client requests and reach only required DNS/signing
  dependencies;
- name-relay can receive relay traffic, reach DNS, and reach approved origin
  ports;
- enterprise control, verifier, OPA, gateway, and backend receive and emit only
  their documented flows.

The Kind workflow pins a supported version/CNI combination, checks enforcement,
and runs one allowed and one denied flow. When no live Kind cluster is
available, server-side or client-side manifest validation is reported as
static evidence only.

### Local secret and bounded-state controls

A shared secure-file helper creates parent directories and temporary files with
restrictive permissions, flushes them, and atomically replaces the target.
POSIX directories use `0700` and private files use `0600`. On Windows the helper
applies and verifies a protected DACL for the current user plus SYSTEM and
Administrators. Failure to enforce the requested access boundary is fatal.

Bootstrap uses that helper for private keys and bearer tokens. Public
certificates and public keys may use ordinary read permissions. A repository
`.dockerignore` excludes `.git`, caches, virtual environments, archives,
`secrets/`, `tokens/`, and generated evidence from every builder context.

The synthetic pool uses a monotonic cursor, a reusable-address heap, and an
expiry heap. Allocation is constant or logarithmic in active state and fails
with `SyntheticPoolExhausted` at the configured hard capacity. The replay cache
uses a dictionary plus expiry heap, rejects new admissions at capacity after
expired entries are removed, and never performs a full dictionary scan.

Name-route admission has conservative per-client and global concurrency/rate
limits before allocation. The anonymous client key thumbprint is the per-client
key; this limits unauthenticated exhaustion without adding ISP subscriber
identity.

Capabilities are normalized into exact ports: `http` authorizes 80, `https`
authorizes 443, and unsupported or empty capability sets are rejected. The
signed binding contains only those derived ports.

## Data flows

### Public ISP name route

1. The Windows client validates the configured CA and opens HTTPS to
   name-control.
2. Name-control validates hostname, session key, capabilities, and admission
   limits before allocating a synthetic mapping.
3. It signs a short-lived binding containing the exact authorized ports.
4. The client connects to name-relay with server-authenticated TLS and presents
   its binding plus fresh Ed25519 proof-of-possession.
5. The relay validates signature, scope, expiry, replay, and destination policy.
6. It resolves the hostname privately, connects only to an allowed literal,
   then relays opaque bytes. The origin address is never returned to the client.

### Enterprise request

1. The client obtains an identity-scoped ticket from the HTTPS control plane.
2. The client sends the ticket over HTTPS to Envoy.
3. Envoy strips untrusted NBSR headers and recreates trusted metadata from the
   real request.
4. The verifier and OPA authorize that exact service, method, and path.
5. Envoy forwards the request to the fixed internal backend mapping.

## Error handling and compatibility

Unsafe configuration and state fail closed with actionable errors:

- missing CA, unreadable CA, invalid certificate, or hostname mismatch prevents
  the connection;
- a blocked or unresolved origin yields relay rejection without a partial
  upstream connection;
- a full replay cache or synthetic pool rejects new admission;
- invalid capabilities return a client error before allocation;
- secure-file permission failure aborts bootstrap and preserves the prior file;
- ambiguous enterprise metadata returns authorization denial.

Existing Ed25519 JWT and proof-of-possession formats remain compatible except
that newly issued bindings may contain a subset of ports. Existing enterprise
OPA policy and fixed upstream routing remain intact.

## Verification strategy

Each security boundary receives a failing regression test before implementation
and a positive control through the same interface. Verification proceeds from
focused tests to the complete Python suite, Ruff, Compose configuration, OPA
tests, Docker image builds, and live Compose attack/legitimate flows. Kind
manifests are validated and live network-policy tests run when a cluster is
available.

The final package is built from the committed feature-branch tree, excludes
Git metadata, credentials, caches, and generated runtime state, is extracted
into a clean directory for revalidation, and is accompanied by a SHA-256 digest.

## Explicit non-goals and residual limits

- No ISP billing, captive portal, subscriber authentication, or mandatory
  client certificate is introduced.
- No TLS interception, content inspection, or destination certificate
  substitution is introduced.
- The trusted private-origin rule is an operator configuration for controlled
  services; a future signed endpoint registry can replace it.
- General UDP, QUIC/HTTP3, raw IP tunneling, production WFP integration, and
  native macOS/iOS/Android clients remain outside this release.
- The previous Deep Scan evidence is retained, but its UI-level final seal
  remains unavailable because discovery orchestration ended in a terminal
  manifest-state error. The remediation report records that tooling limitation
  separately from code verification.
