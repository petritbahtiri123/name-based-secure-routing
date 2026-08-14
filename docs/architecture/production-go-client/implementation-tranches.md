# Recommended future implementation tranches

This is decomposition, not an implementation plan. No tranche is authorized by
this document. Each begins only after its listed protocol/product decisions are
approved and is independently testable.

1. **Platform-independent core skeleton and bounded state models.** Define
   immutable identifiers/handles, typed errors, lifecycle interfaces, limits,
   clock/randomness abstractions, policy inputs, and deterministic state-machine
   tests. No QUIC or OS interception.
2. **Identity and local Authority Provider integration.** Implement approved
   key handles, startup validation, grant acquisition/verification, coalescing,
   cache, renewal, cancellation, revocation freshness, and recovery tests.
3. **Transport Session and Service Channel ownership.** Integrate Go QUIC/TLS
   using verified interop semantics; add reuse keys, pool, selector, independent
   channel authorization, multi-service isolation, expiry/revocation, and
   Go↔Rust tests. No rotation yet.
4. **Stream Credits and Application Stream path.** Implement exact P2D client
   ownership, atomic slots/refill, actual stream-ID binding, payload-before-
   ACCEPT quarantine, forwarding, half-close, cancellation, backpressure, and
   retry boundaries. Preserve all accepted vectors and wire behavior.
5. **Rotation and crash/network recovery.** Add the two-generation state
   machine, proactive triggers, fresh TS-B grants/channels/credits, atomic
   selection, cross-generation revocation, drain/destruction, sleep/network
   changes, crash/restart, and cap-bound adversarial tests.
6. **First user-space proxy adapter.** Add scoped resolver/proxy integration,
   local application attribution, Synthetic-IP mapping/collision containment,
   install/rollback, and end-to-end application tests. State its transparency
   limitations explicitly.
7. **Observability and resource hardening.** Add redacted bounded-cardinality
   metrics/logs, health, overload behavior, idle/soak/GC/goroutine/handle
   measurement, fault injection, and measured defaults for named hardware.
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

The earliest detailed implementation plan should cover only tranche 1 after the
human decisions in the gap register are resolved or explicitly scoped out.
