# NBSR Prototype Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and verify the complete local NBSR security-routing prototype.

**Architecture:** A shared Python package supplies strict JWT and Ed25519 ticket
logic. FastAPI control-plane, verifier, and demo backend services integrate with
OPA and Envoy; Compose network boundaries enforce backend isolation.

**Tech Stack:** Python 3.12, FastAPI, Pydantic, cryptography, PyJWT, httpx,
pytest, OPA, Envoy, Docker Compose, kind.

## Global Constraints

- Ed25519/EdDSA only for routing tickets; explicit algorithm allowlists.
- OPA is authoritative and default-deny.
- Envoy is the exposed enforcement gateway with fixed upstream mapping.
- Docker Compose is mandatory; kind and mTLS are secondary.
- Never expose secrets or backend addressing in public APIs or logs.

---

### Task 1: Security core and tests

**Files:** `tests/test_security.py`, `nbsr/security.py`, `nbsr/config.py`

**Interfaces:** Produce `validate_identity(token, settings)`,
`issue_ticket(subject, request, decision, settings)`, and
`verify_ticket(token, method, path, service, settings)`.

- [ ] Write focused identity and route-ticket tests for valid, expired,
  wrong-issuer/audience/algorithm, tampered, wrong-scope, and required claims.
- [ ] Run `python -m pytest tests/test_security.py -q` and confirm missing-module
  failure.
- [ ] Implement strict validation and compact EdDSA issuance.
- [ ] Re-run the focused test and confirm all cases pass.

### Task 2: Policy and control plane

**Files:** `policy/nbsr.rego`, `policy/nbsr_test.rego`,
`nbsr/control_plane.py`, `tests/test_control_plane.py`

**Interfaces:** `POST /v1/routes/resolve` consumes bearer identity and returns
only `service`, `gateway_url`, `routing_ticket`, and `expires_in`.

- [ ] Write FastAPI tests for authorized and denied decisions.
- [ ] Implement an injectable OPA client with timeout and fail-closed errors.
- [ ] Implement explicit Rego default-deny and structured decision metadata.
- [ ] Run focused Python tests and `opa test policy -v` when OPA exists.

### Task 3: Verifier, gateway, backend, and client

**Files:** `nbsr/ticket_verifier.py`, `nbsr/payments.py`,
`nbsr/demo_client.py`, `gateway/envoy.yaml`, service Dockerfiles.

**Interfaces:** Envoy `ext_authz` sends the original request context; verifier
returns 200 only for a fully scoped ticket; Envoy has one fixed payments cluster.

- [ ] Write verifier endpoint tests for valid/missing/tampered/expired/escalated
  requests and backend endpoint tests.
- [ ] Implement minimal FastAPI services and CLI.
- [ ] Configure Envoy HTTP `ext_authz` and fixed routing.
- [ ] Run focused tests.

### Task 4: Compose deployment and demos

**Files:** `compose.yaml`, `.env.example`, `scripts/bootstrap.*`,
`scripts/demo.*`, `scripts/test.*`

**Interfaces:** Published ports are control plane `8000` and Envoy `8080`;
payments has no host port. Client and protected networks do not directly join.

- [ ] Add non-root images, health checks, key bootstrap, and readiness.
- [ ] Implement nine labeled scenarios and a mandatory pass/fail summary.
- [ ] Validate `docker compose config`, build, health, demo, and E2E when Docker
  is installed.

### Task 5: kind and documentation

**Files:** `deploy/kind/*`, `README.md`, `SECURITY.md`,
`docs/{architecture,security-model,threat-model,demo-script,build-week-submission}.md`,
`docs/decisions/*`.

**Interfaces:** kind reuses the same images; NetworkPolicies permit only the
documented flows.

- [ ] Add namespace, workloads, services, configuration, secrets template,
  policies, cluster config, and lifecycle scripts.
- [ ] Document exact setup, trust boundaries, commands, limitations, evolution,
  submission copy, and three-minute recording flow.
- [ ] Run static YAML validation when kubectl exists and reconcile docs against
  real commands.

### Task 6: Final skeptical verification

- [ ] Run focused tests, full Python suite, lint/format checks, OPA tests,
  Compose validation/build/demo, and kind validation where tools exist.
- [ ] Inspect tracked/untracked files for secrets, fail-open behavior, backend
  exposure, unsafe algorithms, startup races, and misleading claims.
- [ ] Record unavailable tools and exact owner commands without fabricating
  results.
