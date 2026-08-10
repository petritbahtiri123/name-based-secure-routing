# P1D transport-session rotation security analysis

## Decision

Outcome **C — DESIGN BLOCKED BY FROZEN PROTOCOL/OWNERSHIP SEMANTICS**. The protocol can establish TS-B independently and securely while TS-A exists, but the current production boundary has no owner that can (a) obtain fresh RouteGrant/channel authority before the old channel closes, (b) atomically select TS-B for new application flows, and (c) drain/retire TS-A without exposing that transition. Choosing those semantics here would invent an application-facing session pool and authority-refresh contract. Production rotation therefore fails gates 3 and 5 and is not authorized.

## Complete lifecycle trace

1. **Transport creation.** `connect` and `TransportListener::accept_one` create distinct Quinn connections (`quinn_adapter.rs:64,575`). Each successful TLS/ALPN/peer-policy authentication returns one `AuthenticatedConnection` (`quinn_adapter.rs:593`). Parallel calls can coexist; there is no singleton restriction.
2. **Authentication.** `authenticate_connection` validates ALPN, certificate identity, local role, and peer policy before constructing the authenticated wrapper. `ConnectionBindingCapability` is created per wrapper and is used as an unforgeable same-connection capability.
3. **ControlSession creation.** `ControlSession::new_inner` copies authenticated peer/role/ALPN and the connection capability, initializes fresh `request_ids`, `ChannelStreams`, state, deadlines, and diagnostics (`session.rs:164-196`). It has a hard one-hour lifetime (`session.rs:38`).
4. **RouteGrant binding.** CLIENT_HELLO/EDGE_HELLO establish the session ID and bind client and edge nonces plus the client-session public-key thumbprint. `accept_route_open` requires the established session ID, fresh request ID, increasing sequence, verified signed RouteGrant, and admission capacity before committing (`session.rs:418-464`; `admission.rs:600-646`).
5. **Service Channel admission.** A channel begins as a candidate, then the live TLS exporter derived from the exact authenticated connection and service context is installed before the channel becomes bound. Every sibling channel receives independent grant/nonce/admission and binding.
6. **Application Stream admission.** `authorize_stream_open` requires an active session, exact session/request/sequence binding, a bound active channel, and `ChannelStreams::prepare_open`; it reserves audit capacity before `commit_open` and only then commits request/sequence state (`session.rs:589-620`). The adapter checks the permit against the actual Quinn stream ID before payload exposure.
7. **Replay ownership.** `ControlSession` owns one `ChannelStreams`; its `used_stream_ids` set is session-wide across channels (`session.rs:84`; `channel_streams.rs:12-76`). Request IDs and directional monotonic sequences are separate session-local replay owners.
8. **Session close/drop.** Quinn close ends the authenticated transport (`quinn_adapter.rs:829`). Dropping `ControlSession` drops all request/channel/stream replay containers and completes the transport-session diagnostic (`session.rs:1391`).
9. **Channel cleanup.** Release/reset removes live stream state, while channel close/revoke/drain changes the channel registry and adapter tracking. It deliberately does not remove committed IDs from `used_stream_ids`; `channel_streams.rs:384` tests cross-channel and post-release replay.
10. **Request-ID cleanup.** `request_ids` has no per-request eviction. It is released only with its `ControlSession`, matching the session replay scope.
11. **Resume/migration.** Same-edge resume is explicit and single-use. `SameEdgeResumeManager::issue` accepts only a normally closed old channel, not active, revoked, or forced-drained authority (`resumption.rs:184`; `resumption.rs` test at line 1546). Preflight requires different connection capability and session ID. Consume additionally requires different channel ID, grant digest, route ID, grant nonce, client nonce, and edge nonce (`resumption.rs:275-488`). QUIC path migration, where Quinn preserves the connection, preserves the same Transport Session and is not rotation.
12. **Destination cleanup.** Destination adapter close/reset clears transport tracking; dropping destination `ControlSession` releases replay history. Admission registries/tombstones live only in that session object.
13. **Source cleanup.** Source streams stay owned by the `AuthenticatedConnection` that opened them. Existing APIs expose a single connection/session/permit to the caller; there is no production multi-session stream selector or application-flow migration owner.

## Freshness and authority

Cryptographic freshness is a new authenticated QUIC/TLS connection plus a new `ConnectionBindingCapability`, new nonzero session ID, fresh CLIENT_HELLO client nonce/session key, fresh EDGE_HELLO edge nonce, and independently admitted/bound channels. Static edge identity, the configured trust profile, trusted issuer list, service/policy equivalence, and peer identity may legally be the same.

The following must not cross as authority: connection capability/exporter, session ID, control request/sequence state, channel ID, route ID, RouteGrant digest and nonce, client/edge nonces, stream permits, `used_stream_ids`, resume preflights/handles after consumption, downgrade state, or revoked/expired authority. Existing resume code enforces these constraints.

## Make-before-break finding

Two independent authenticated connections and ControlSessions can exist concurrently, so transport-level make-before-break is mechanically possible. Ordinary fresh RouteGrant admission can also occur on TS-B while TS-A is active. What does not exist is the production orchestration contract that obtains that fresh authority on demand and maps a logical service/application listener to old and new session/channel pairs. `AuthenticatedConnection::open_session_stream` accepts a permit for exactly one connection; it neither pools connections nor selects among them. Same-edge resume cannot fill this gap because issuance requires the old channel to be normally closed, so it is break-before-resume by design.

## Race and failure matrix

| Case | Proven safe model outcome | Production orchestration status |
|---|---|---|
| Stream before boundary | Stays owned by TS-A | Existing single-session behavior |
| Stream at/after boundary | TS-B only after independent admission | No atomic selector owner |
| TS-A drains | Existing streams remain TS-A; replay retained | Session drain exists |
| TS-A closes first | No authority transfers | Application continuity undefined |
| TS-B admission fails | TS-A state remains intact | Retry/fallback selection undefined |
| Connection failure during rotation | No fail-open authorization | Application retry ownership undefined |
| Simultaneous streams | Model selects only an admitted session | No production synchronization point |
| Channel revoke | New streams reject on revoked channel | Cross-session revoke fan-out owner undefined |
| Authority revoke | Fresh admission must recheck authority | Refresh/fan-out contract undefined |

All undefined cases must fail closed. That preserves security but cannot prove the required absence of observable application-flow disruption.

## Six implementation gates

1. No replay-security weakening: **PASS** in the model; TS-A retains full history until retirement and TS-B begins empty only after independent authority.
2. No authority resurrection: **PASS**; stale channel/grant/binding and consumed resume material reject.
3. No protocol ambiguity requiring human choice: **FAIL**; fresh authority acquisition, cross-session revocation fan-out, stream-selection ownership, and application retry behavior are unspecified.
4. Existing protocol supports fresh session establishment safely: **PASS**.
5. Rotation bounded and deterministic: **FAIL** at production scope; counting is possible, but there is no deterministic production transition owner or configured policy surface.
6. Failure modes remain fail closed: **PASS**; the model rejects ambiguity and existing admission is mutation-ordered.

Because not all six pass, no production implementation, smoke, paired BEFORE/AFTER campaign, or long-session run is eligible.

## Rotation policy sizing (not configured)

No trigger is installed. P1B measured about 44.98-45.78 private bytes and 52.64-53.19 working-set bytes per committed history entry at 1,215,000 entries. A future approved local policy could start from an explicit 16 MiB replay-state working-set budget, reserve 25% operating margin, and use the conservative upper proxy: `floor(16 MiB * 0.75 / 53.19) = 236,565` entries, then choose a reviewed bound at or below that value. This is only sizing evidence, not a protocol guarantee or an approved constant.

## Exact decision required

Freeze one application-facing rotation contract that names the owner of a service's active/standby session pair, defines how fresh RouteGrants are obtained before cutover, atomically selects the independently admitted TS-B channel for new flows, fans out revocation to both generations, defines retry behavior if TS-B fails, and retires TS-A only after its in-flight streams drain. It must explicitly state that same-edge resume is not used to transfer active-channel authority. Without that decision, implementing rotation in `ControlSession` or `AuthenticatedConnection` would place cross-session authority above the layer that currently owns it.
