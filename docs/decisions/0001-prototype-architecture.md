# ADR 0001: Prototype architecture

Accepted decisions: Python/FastAPI for small auditable services; Docker Compose
as the mandatory path and kind as secondary; signed JWT identity with optional
local mTLS material but no SPIRE; Ed25519 ticket signatures; OPA explicit
default deny; Envoy enforcement with an external verifier; no database; and a
fixed service-to-upstream mapping rather than dynamic registration.

These choices minimize hackathon operational dependencies while preserving the
important trust boundaries. They trade away replay storage, production
identity lifecycle, dynamic discovery, HA, and managed key rotation.
