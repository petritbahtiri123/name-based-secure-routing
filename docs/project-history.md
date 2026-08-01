# NBSR project history

This document records the public technical evolution of Name-Based Secure Routing (NBSR). Git commits, tags, release artifacts, and protocol documents remain the authoritative dated evidence.

## Original proof of concept — July 2026

NBSR began as an OpenAI Build Week proof of concept demonstrating that access to a logical service name could be authorized before traffic reached a protected backend.

The original prototype used a FastAPI control plane, Ed25519 workload identity, short-lived route tickets, OPA default-deny policy, Envoy external authorization, isolated container networks, and deterministic allow/deny demonstrations.

The `main` branch preserves that original proof-of-concept lineage. It is not the authoritative protocol-development branch.

Key baseline commit:

- `1938154d498b32d81a3564319969430644e8a688` — self-contained Build Week video-demo preflight.

## Name-routing expansion

After the initial prototype, development expanded from enterprise service authorization into name-based secure routing:

- DNS-compatible application behavior;
- synthetic addresses returned to clients;
- origin addresses retained internally;
- source and destination edge separation;
- signed route capabilities;
- replay and destination-policy enforcement;
- Windows ownership recovery;
- ISP-profile and Kubernetes demonstrations.

## Protocol Vision V3 and V3.6

The architecture was reworked into a resolver-first protocol model. The central rule became:

> Every successful NBSR resolution on an upgraded network returns a scoped Synthetic IP, and connecting to that address creates or reuses an authorized secure route while the origin remains internal.

Vision V3.6 established the separation between:

- Name and Resolution Plane;
- Route Authorization Plane;
- Transport Session and Service Channel Plane;
- internal OriginSet and destination connector behavior;
- legacy compatibility and migration mechanisms.

The authoritative vision is `docs/architecture/NBSR_Protocol_Vision_V3.6.md`.

## WP0 — documentation alignment

WP0 aligned terminology, architecture, status reporting, compatibility boundaries, and implementation sequencing with the resolver-first design. It also established explicit non-claims so prototype evidence would not be confused with production readiness or full protocol conformance.

## WP1 — deterministic protocol data boundary

WP1 established the Core v0.1 protocol-data foundation:

- frozen message and error registries;
- bounded deterministic CBOR;
- six closed protocol models and schemas;
- COSE Sign1 with Ed25519;
- explicit algorithm and key binding;
- valid and invalid deterministic vectors;
- property-based mutation and parser testing;
- a documented cross-language wire contract;
- a stable Python protocol package boundary.

This work provides deterministic signed objects and validation behavior. It does not by itself provide an integrated production runtime.

## WP2A — Name Node core

WP2A implemented a lab-scale synthetic-only Name Node core:

- signed service records;
- bounded local registry behavior;
- resolution-state lifecycle;
- bounded IPv4 and IPv6 synthetic allocation;
- expiry, collision, rollback, and equivocation controls;
- privacy-safe observability;
- loopback UDP and TCP DNS-compatible access;
- internal legacy DNS-derived OriginSet support.

The client-visible answer remains synthetic. Origin reachability information stays internal.

## Core v0.2 vectors and independent verification

Core v0.2 work added deterministic session, route, proof, binding, and version-dispatch artifacts. A dependency-free Node.js verifier independently checks the vector package, providing cross-language conformance evidence without claiming a second complete runtime implementation.

## WP3 — single-service QUIC transport slice

WP3 implemented an origin-free Rust QUIC/TLS laboratory boundary using Quinn and rustls:

- TLS 1.3 mutual authentication;
- exact NBSR ALPN;
- authenticated CLIENT_HELLO and EDGE_HELLO exchange;
- peer SAN and policy-identity binding;
- signed RouteGrant admission;
- nonce, sequence, expiry, replay, service, port, transport, and capacity checks;
- correlated ROUTE_ACCEPT behavior;
- one admitted Service Channel;
- one bounded application stream;
- fail-closed behavior without fallback from Core v0.2 to Core v0.1.

This slice intentionally does not yet select an OriginSet, connect to a real origin, integrate the Python NameRelay, or reuse one Transport Session for multiple services.

## Active development branch

The active protocol research and reference-implementation branch is:

```text
codex/nbsr-v3-wp0-wp1
```

It is intentionally separate from `main` so the original proof of concept and the later protocol evolution remain independently inspectable.

## Licensing

The active protocol branch is licensed under the Apache License 2.0. The license permits use, modification, redistribution, and commercial implementation subject to its terms, including preservation of the license and applicable notices. Git history records the dated development and authorship of the repository's code and documentation.

## Current boundary

The project has credible protocol components and verified laboratory vertical slices, but it does not yet claim:

- production readiness;
- global federation;
- complete Core conformance;
- a production recursive resolver;
- real multi-operator deployment;
- integrated end-to-end origin forwarding through the Rust transport;
- distributed replay, revocation, or high-availability guarantees;
- independent complete runtime interoperability.

For the current evidence-backed status, use `docs/protocol/status.md` rather than this historical summary.
