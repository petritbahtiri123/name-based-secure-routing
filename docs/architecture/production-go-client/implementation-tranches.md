# Recommended future implementation tranches

This is decomposition, not an implementation plan. No tranche is authorized by
this document. Each begins only after its listed protocol/product decisions are
approved and is independently testable.

1. **Platform-independent core skeleton and bounded state models.** Define
   immutable identifiers/handles, typed errors, lifecycle interfaces, limits,
   clock/randomness abstractions, policy inputs, and deterministic state-machine
   tests. Include fixed-width ServiceHandle allocation plus bounded MappingTable,
   ServiceTable, and StreamTable with capacity, stale-handle, teardown, and
   allocation tests. No QUIC or OS interception.
2. **Identity and NBSR Authority Control Plane integration.** After approval of
   [the Tranche 2 design](tranche2-identity-authority-control-plane.md) and its
   separately gated ACP wire profile, implement identity/key references, the
   transport-neutral `AuthorityProvider`, independent grant verification,
   bounded coalescing/cache/idempotency, renewal, freshness, generation barrier,
   recovery, and deterministic tests. Keep HTTP/TLS and all backend mechanics
   outside session/stream components.
3. **Transport Session and Service Channel ownership.** Integrate Go QUIC/TLS
   using verified interop semantics; add reuse keys, pool, selector, independent
   channel authorization, local ServiceHandle binding over existing channel IDs,
   multi-service isolation, expiry/revocation, and Go↔Rust tests. Prove one TS
   carries many SCs without destination-IP routing. No rotation yet.
   **Implementation status (2026-08-24):** the production Go ownership layer,
   sealed-authority admission material, bounded TS/SC lifecycle, commit barrier,
   and deterministic teardown are implemented; see
   [`tranche3-implementation-status.md`](../../protocol/tranche3-implementation-status.md).
4. **Stream Credits and Application Stream path.** Implement exact P2D client
   ownership, atomic slots/refill, actual stream-ID binding, payload-before-
   ACCEPT quarantine, forwarding, half-close, cancellation, backpressure, and
   retry boundaries. Preserve all accepted vectors and wire behavior.
   **Implementation status (2026-08-24):** bounded credit and Application
   Stream ownership, payload gating, final commit barrier, recursive teardown,
   and real Go-to-Rust admission/refill interoperability are implemented; see
   [`tranche4-implementation-status.md`](../../protocol/tranche4-implementation-status.md).
5. **Rotation and crash/network recovery.** Add the two-generation state
   machine, proactive triggers, fresh TS-B grants/channels/credits, atomic
   selection, cross-generation revocation, drain/destruction, sleep/network
   changes, crash/restart, and cap-bound adversarial tests.
6. **Resolution to one shared Synthetic IP and secure routing.** Add canonical
   resolution provenance, immutable bounded mappings, and an explicit local
   SOCKS5-domain/HTTP CONNECT adapter that supplies per-flow local correlation
   before authority selection. Reuse the existing authority, TS, SC, credit,
   and Application Stream stack without wire changes. This explicit-proxy
   tranche makes no transparent-interception or install/rollback claim.
   **Implementation status (2026-08-24):** the production Go bounded resolution,
   mapping, correlation, and secure-routing integration is implemented; see
   [`tranche6-implementation-status.md`](../../protocol/tranche6-implementation-status.md).
7. **Observability and resource hardening.** Add redacted bounded-cardinality
   metrics/logs, health, overload behavior, idle/soak/GC/goroutine/handle
   measurement, fault injection, and measured defaults for named hardware.
   **Implementation status (2026-08-25):** bounded identifier-free aggregate
   observability, usage/health snapshots, early-disconnect correlation cleanup,
   and current-machine race/churn evidence are implemented; see
   [`tranche7-implementation-status.md`](../../protocol/tranche7-implementation-status.md).
   Shipping defaults and production sizing remain unestablished.
8. **Linux/router TUN adapter.** After separate platform approval, prove route
   ownership, DNS/capture, MTU, bypass blocking, privilege containment,
   upgrade/rollback, and embedded resource behavior without changing the core.
9. **Windows native interception adapter.** After separate platform approval,
   build the signed service/WFP boundary, app identity mapping, network-change
   handling, driver/update/rollback safety, and Windows-specific adversarial
   validation.
10. **Multi-host and operational acceptance.** Run matched Go↔Rust multi-service
    E2E, revocation/rotation/failure campaigns, authority outage/recovery,
    upgrade compatibility, privacy/log review, independent security review, and
    hardware-specific benchmark methodology before any production claim.

After human approval of this amendment, the design is ready for a detailed plan
covering tranche 1 only; no additional protocol, authority-control-plane,
resolver, revocation, or platform decision is needed for those internal bounded
state models. The plan must record all later unresolved gaps as explicit
exclusions and must not plan wire changes, live authority-provider integration,
or platform interception ahead of their separate approvals.
