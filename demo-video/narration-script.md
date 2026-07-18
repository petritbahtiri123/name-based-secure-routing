# NBSR Demo Narration

**Target:** 2 minutes 48 seconds  
**Word count:** 297 words

## 0:00–0:12 — Title

Traditional DNS tells a workload where a service is. It does not decide whether
that workload should reach it. Name-Based Secure Routing adds identity, policy,
and short-lived authorization to that route.

## 0:12–0:35 — Architecture

A client proves its workload identity to the NBSR control plane. The control
plane asks an OPA default-deny policy. The control plane alone holds the private
ticket-signing key. When allowed, it creates a short-lived Ed25519 routing
ticket. The verifier receives only the public key. Envoy uses external
authorization and a fixed allowlisted route to the private payments service.

## 0:35–1:55 — Live demonstration

The client cannot connect to that backend directly. All five Docker Compose
services are ready. The allowed workload resolves payments.internal and reaches
the service through Envoy. The denied identity receives no route. An unknown
service is also denied by default.

A missing ticket is rejected. Changing real decoded signature bytes is also
rejected. An automated regression test protects the tamper case. The ticket
cannot escalate its method or path. The client cannot connect directly to the
payments backend, proving real network isolation. The short-lived ticket
expires and is rejected. All eight real mandatory scenarios pass.

## 1:55–2:15 — Security explanation

Tickets bind workload, service, method, path, gateway audience, and expiration.
Envoy fails closed. Clients cannot choose an upstream, and the backend has no
published port.

## 2:15–2:33 — GPT-5.6 and Codex

Humans directed the concept, architecture, security requirements, technology,
scope, fail-closed criteria, testing, and submission decisions. GPT-5.6 and
Codex accelerated the FastAPI services, OPA and Envoy integration, Docker and
Kubernetes resources, tests, documentation, live validation, and correction of
the Base64 URL tamper-test flaw.

## 2:33–2:48 — Closing

Compose was validated live. Kubernetes resources passed offline validation, but
live kind was not tested. This is a validated prototype, not intended for
production, and it does not replace DNS. Identity and policy decide the
temporary route. The public repository is available on GitHub.

### Optional pronunciation

- **Envoy:** EN-voy
- **Ed25519:** ed two-five-five-one-nine
- **OPA:** oh-pah
- **SPIFFE:** spiffy
