# Name-Based Secure Routing (NBSR)

> **North Star:** Every successful NBSR resolution returns a scoped synthetic
> IP; connecting to it creates or reuses a secure route while the origin stays
> internal.

NBSR is being developed as a DNS-compatible name-resolution and secure-routing
protocol. An upgraded NBSR Name Node returns a scoped synthetic IP for every
successfully resolved name. NBSR-aware services use signed identity and policy;
legacy DNS may supply constrained internal reachability metadata. Neither path
returns the origin IP to the client or permits direct-origin fallback.

The long-term deployable unit has two isolated planes: a Name/Resolution Plane
and a Secure Route/Tunnel Plane. A Source NBSR Edge acts for ordinary devices
behind an upgraded router, enterprise gateway, or ISP, so the first no-agent
lab does not require per-device NBSR software. Networks that have not upgraded
continue using conventional DNS and IP connectivity.

This repository is a hardened local protocol vertical slice and enterprise
authorization proof of concept. It is not Protocol Core v0.1 and not a
production system.

## Authoritative direction and implementation status

- [NBSR Protocol Vision V3.6](docs/architecture/NBSR_Protocol_Vision_V3.6.md)
  is the authoritative architecture and implementation program.
- [V3.6 decisions and compatibility impact](docs/protocol/v3.6-decisions.md)
  preserve the frozen Core v0.1 decisions and list unresolved human gates.
- [Protocol terminology](docs/protocol/terminology.md) defines the canonical
  project vocabulary.
- [Implementation status](docs/protocol/status.md) separates verified
  prototype behavior from partial, planned, and normative Core v0.1 behavior.
- [V3.6 protocol roadmap](docs/superpowers/plans/2026-07-28-v3.6-protocol-roadmap.md)
  defines gated WP2-WP6 sequencing and does not authorize runtime work.
- [Standards reuse matrix](docs/protocol/standards-reuse-matrix.md) and
  [minimal NBSR surface](docs/protocol/minimal-nbsr-protocol-surface.md)
  separate reused Internet standards, NBSR profiles, and genuinely new NBSR
  semantics.
- Vision V2 and the original feasibility study remain available under
  [`docs/history`](docs/history/README.md) and
  [`docs/research`](docs/research/README.md).

## What is functional

### ISP-profile registered-name routing

An application requests the explicitly registered name `facebook.test`.
Name control returns a synthetic local address and a short-lived Ed25519-signed
route capability. The capability is bound to the canonical name, stable route
ID, gateway, allowed port, exact resolved endpoint set, policy
version/fingerprint, client session, and expiry.

The TLS 1.3 relay independently enforces its local default-deny registry,
re-resolves immediately before connection, and rejects changed, ambiguous, or
out-of-policy endpoints. The client never receives the durable origin address.
HTTPS remains opaque through the relay, so the client validates the origin
certificate and preserves `facebook.test` as SNI and Host.

Port 80 is a compatibility demonstration inside the authenticated
client-to-relay TLS channel. It sends no NBSR credential to the origin and is
not classified as native end-to-end authenticated NBSR.

### Optional enterprise authorization

The separate enterprise path validates an Ed25519 workload JWT, asks OPA over
TLS 1.3 mTLS, issues a short-lived method/path/service-scoped ticket, and has
Envoy enforce that ticket through an mTLS external-authorizer before a fixed
mTLS backend route.

```mermaid
flowchart LR
    C["Workload"] -->|"JWT + logical service"| CP["Control plane"]
    CP -->|"mTLS decision"| OPA["OPA default deny"]
    CP -->|"Ed25519 route ticket"| C
    C -->|"HTTPS request + ticket"| E["Envoy"]
    E -->|"mTLS ext_authz"| V["Verifier"]
    E -->|"mTLS fixed upstream"| P["Payments"]
```

Enterprise tickets remain short-lived bearer credentials and can be replayed
within their valid lifetime. Channel binding or a distributed one-time replay
store is not implemented.

## Security boundaries

- Arbitrary public hostnames, public IPs, destination overrides, private/special
  addresses, Unicode ambiguity, stale policy, and DNS rebinding fail closed.
- Public global-unicast status is never route authorization.
- The ISP relay is not connected to the enterprise protected network.
- Payments, verifier, OPA, and the demo origin have no host publications.
- Developer ingress ports bind explicitly to `127.0.0.1`.
- Every sensitive cross-container enterprise hop uses verified TLS 1.3 mTLS.
- Generated secrets, tokens, and certificates are ignored and excluded from
  Docker and release archives.

See [architecture](docs/architecture.md),
[security model](docs/security-model.md), [threat model](docs/threat-model.md),
the [hardening report](docs/security-hardening-report.md), and the
[current V3.6 implementation status](docs/protocol/status.md).

## Requirements

- Docker Desktop with the Linux engine and Compose v2
- Python `>=3.12,<3.14` for local development
- OPA CLI for direct Rego tests
- Kind v0.32+ and kubectl for the Kubernetes reference deployment

The primary container runtime is digest-pinned Python 3.13.14. Exact runtime and
development constraints are in `constraints/`.

## Docker Compose demo

Windows PowerShell:

```powershell
./scripts/demo.ps1
```

Linux/macOS:

```bash
./scripts/demo.sh
```

The wrapper regenerates ignored local credentials, performs a fresh Compose
build/deployment, and runs eight mandatory enterprise allow/deny scenarios.
Expected denials cover unauthorized identity, unknown service, missing ticket,
tampering, method/path escalation, direct backend access, and expiry.

With the stack running, execute the registered-name demonstration:

```powershell
./scripts/name-route-demo.ps1
```

or:

```bash
./scripts/name-route-demo.sh
```

Published developer endpoints are loopback-only:

| Port | Endpoint |
|---|---|
| 8000 | Enterprise TLS control plane |
| 8080 | Enterprise TLS Envoy gateway |
| 8443 | ISP TLS name relay |
| 8444 | ISP TLS name control |

Clean up:

```powershell
docker compose down -v --remove-orphans
```

## Kind reference deployment

The Kind workflow disables Kind's default CNI and installs Calico v3.32.1 from
a pinned URL only after verifying its SHA-256. It then deploys namespace-wide
default-deny policy and runs positive/negative Service IP, Pod IP,
cross-namespace, metadata, and link-local probes.

```powershell
./scripts/kind-up.ps1
```

or:

```bash
./scripts/kind-up.sh
```

Remove all local cluster resources:

```powershell
./scripts/kind-down.ps1
```

## Tests

Install the exact development set:

```bash
python -m pip install --constraint constraints/dev.txt -e ".[dev]"
```

Run:

```bash
python -m pytest -q
python -m ruff check .
python -m ruff format --check .
opa test policy -v
docker compose config --quiet
```

Python 3.12.13 and 3.13.14 are tested. Python 3.14 is intentionally outside the
declared range.

## Deterministic release archive

Both wrappers require an explicit Git ref and reject tracked dirty source:

```powershell
./scripts/package-release.ps1 HEAD
```

```bash
./scripts/package-release.sh HEAD
```

Packaging uses a Git-derived source set, rejects prohibited/secret-like
content, writes a deterministic inventory and ZIP under ignored `dist/`,
re-extracts and compares the archive, runs pytest plus Ruff from the extracted
copy in digest-pinned Python 3.13.14, and writes a SHA-256 sidecar.

## Explicit limitations

Not implemented: the universal NBSR Name Node, DNS-backed OriginSet adapter,
native signed OriginSet publication, a normative QUIC Transport Session,
multi-service Service Channels, channel cryptographic separation, active lease
renewal, key rotation, distributed revocation, live migration/resumption or
handover, regional HA, real ISP federation, subscriber billing, arbitrary UDP,
mobile wake-up integration, production PKI/HSM, durable distributed replay
state, a signed Windows Filtering Platform driver, or independent
interoperable implementations.

The current Windows adapter behavior is unit/in-process tested. It is not a
validated full-device Windows networking deployment.
