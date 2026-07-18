# Name-Based Secure Routing (NBSR)

NBSR turns a logical service name into an authenticated, policy-authorized,
temporary route. It is a local hackathon prototype, not a production system.

DNS answers “where?” but not “may this workload access this service, using this
method and path, right now?” NBSR validates workload identity, asks OPA, issues
a 60-second Ed25519 ticket, and has Envoy enforce that ticket before reaching a
backend that clients cannot address directly.

```mermaid
flowchart LR
  C["Workload client"] -->|"JWT + service name"| CP["Control plane"]
  CP -->|"decision query"| OPA["OPA"]
  CP -->|"Ed25519 route ticket"| C
  C -->|"ticket + request"| E["Envoy gateway"]
  E -->|"ext_authz"| V["Ticket verifier"]
  E -->|"fixed route"| P["Protected payments"]
```

```mermaid
sequenceDiagram
  participant C as Allowed client
  participant CP as Control plane
  participant O as OPA
  participant E as Envoy
  participant V as Verifier
  participant P as Payments
  C->>CP: Resolve payments.internal + workload JWT
  CP->>O: Identity, service, method, path
  O-->>CP: Explicit allow + scope
  CP-->>C: 60-second Ed25519 ticket
  C->>E: GET + NBSR ticket
  E->>V: Authorize actual method/path
  V-->>E: Allow
  E->>P: Fixed upstream request
  P-->>C: Demo response
```

```mermaid
sequenceDiagram
  participant C as Denied client
  participant CP as Control plane
  participant O as OPA
  C->>CP: Resolve payments.internal
  CP->>O: client-denied
  O-->>CP: Default deny
  CP-->>C: 403 without ticket
```

```mermaid
flowchart TB
  subgraph Client["Client trust boundary"]
    C["Demo clients"]
  end
  subgraph Control["Control boundary"]
    CP["Control plane (identity public key, ticket private key)"]
    O["OPA"]
  end
  subgraph Protected["Protected boundary"]
    E["Envoy"]
    V["Verifier (ticket public key)"]
    P["Payments (no host port)"]
  end
  C --> CP
  C --> E
  CP --> O
  E --> V
  E --> P
```

## Quick start

Prerequisites: Docker Desktop with Compose v2. On Windows:

```powershell
./scripts/bootstrap.ps1
docker compose up -d --build
./scripts/test.ps1
./scripts/demo.ps1
```

On Linux/macOS:

```bash
chmod +x scripts/*.sh
./scripts/bootstrap.sh
docker compose up -d --build
./scripts/test.sh
./scripts/demo.sh
```

Only ports 8000 (control plane) and 8080 (Envoy) are published. The payments
service is on an internal protected network. The demo prints a scenario table
and exits nonzero on any mandatory mismatch.

For kind, install Docker, kind, and kubectl, then run `./scripts/kind-up.ps1`
or `./scripts/kind-up.sh`; inspect with `kubectl -n nbsr get
all,networkpolicy`; remove with the matching `kind-down` script. The kind path
is secondary to Compose.

## Tests and troubleshooting

Run `python -m pip install -e ".[dev]"` and `python -m pytest -q` for local unit
tests. Run `opa test policy -v` for policy tests. If startup fails, regenerate
local keys with `scripts/bootstrap`, inspect `docker compose ps`, and then
`docker compose logs <service>`. Tokens expire after eight hours; rerun
bootstrap before a new demo. Do not commit `secrets/` or `tokens/`.

## Security model and limitations

The identity JWT and route ticket use separate Ed25519 keys and explicit EdDSA
allowlists. Issuer, audience, time, SPIFFE-like subject, service, method, path,
and required claims are checked. OPA and the verifier fail closed. Envoy has a
fixed upstream; the public API never returns backend addressing.

Tickets are bearer credentials and this prototype has no replay cache, rate
limiting, HA, key rotation protocol, full SPIFFE/SPIRE, or production PKI. The
optional bootstrap CA is local demonstration material; JWT is the reliable
demo identity path. Production evolution should add SPIFFE/SPIRE or cloud
workload identity, managed rotation, replay controls, hardened mTLS, audit
storage, rate limits, and HA policy/enforcement services.

## Build Week notes

GPT-5.6 and Codex accelerated implementation, test generation, cross-platform
scripts, and security review. Human-directed decisions remain the trust model,
OPA default-deny policy, Ed25519 key separation, Envoy enforcement boundary,
fixed upstream mapping, and the decision not to claim production readiness.
See [submission draft](docs/build-week-submission.md) and
[three-minute demo](docs/demo-script.md). Before submission, run `/feedback`
and replace the visible session-ID placeholder with the real value.
