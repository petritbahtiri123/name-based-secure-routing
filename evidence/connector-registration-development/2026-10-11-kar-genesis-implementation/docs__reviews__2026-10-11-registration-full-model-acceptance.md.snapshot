# Full-model registration acceptance matrix

Status: required obligations, not runtime acceptance. Controller-only fallback is
superseded after the 2026-10-11 pause and independent security review. Stage 3 is
partial. No registry flag, source overlay or threshold byte definition is changed.

| Obligation | Required acceptance / negative case | Existing anchor and remaining gap |
|---|---|---|
| Target controller | Exact independently configured controller/operator for typed target; unrelated valid signer cannot act | revocation.py authorize mode 1; actual controller mapping/provider provenance absent |
| Normal 3/5 | Distinct eligible authorities and organizations, exact governing policy and all bound context; 2/5 or a controller cannot substitute | separate approved local normal-revocation-conformance-v1 amendment now covers the mapping; real accepted-context provenance/currentness remain absent. global-trust-v1 is not revocation |
| Emergency 2/5 | Exact authenticated quorum; nonterminal DENY_NEW_USE only, duration <=300 seconds; reject grant/restore/termination | typed-record validator + deny-only-emergency-v1 literal fixtures; producer/runtime composition absent |
| Every dependency | Authenticated governing profile, scope, complete closure and current revision; local profile selection cannot erase obligations | connector profile 919-935; runtime governance resolver absent |
| Signer purpose | KAR signed by IDENTITY_ROOT; authorized transport key purpose14 separate. Other signatures need exact applicable purpose | federation/cose.py; raw cryptographic success must never itself become authority |
| Forged/unsupported inputs | Invalid bytes/signatures or unrelated claims cannot mutate readiness. Independently proved freshness loss is separate; valid applicable termination must be enforced | new native primitive has no readiness/owner access; full dispatcher remains absent |
| Replay/restart | Exact request/session/counter plus authenticated non-regressing lineage/denial floors; old signed bootstrap cannot restore authority | offline counters and local persistence tested; approved exact-root trial passed private write/reopen and injected post-replacement repair. Process-death/power-loss and independently trusted bootstrap floors remain unresolved |
| Uncertain time | Expiry latest plausible UTC; event effective_at earliest plausible UTC; monotonic progress, invalid clock latch, no early termination | injected timer fixtures only; real-clock policy/source unresolved |
| Queue/effective revision | Future enqueue changes no eligibility; unrelated queue mutation cannot stale an applicable event | design constraint; real producer/dispatcher absent |
| Retention/capacity | Bounded pending state; no tombstone eviction/resurrection, no arbitrary service-lifetime event cap; failure retains quota | 64 is only optional test-inventory guard; service compaction unresolved |
| Active work | Admission expiry != ongoing expiry; deny-new preserves independently bounded work; applicable termination overrides grace; repeated drain cannot restart grace | connector model/timer tests; no live download acceptance |
| Cleanup | Failed/unconfirmed close retains ownership, exact confirmation needed, no premature replacement | existing Go/Rust cleanup tests; no new live shutdown proof |
| Threshold container | Exact existing Option C, protected headers, policy/group/scope/lineage/action/profile/capability/session binding; no substituted bare Sign1 list | retained supplement, allocation and 89 literal fixtures; runtime authority provenance unresolved |
| Required witness checkpoint | Authenticate exact log checkpoint/consistency and witness purposes; match record reference, quorum, replay and continuity; stale idempotent evidence must fail | local signed witness composition and separate approved v2 full-record inclusion covered; real configuration provenance and independently retained restart floors remain unproven |
| Exact record inclusion | Approved canonical leaf binds immutable signed record to verified checkpoint without self-reference | approved local v2 full-record inclusion implemented with prior anchor and detached evidence; F=A/F=C and event bindings tested. Historical v1 semantics unchanged; real configuration provenance and durable restart remain open |
| Runtime guard | No component result can admit registration until all applicable modes authenticated/enforced; no narrower operational fallback | new primitive cfg(test), integration-test target only, no Authority implementation or receipt/event constructor |

## Implemented slice and its limits

Native exact tagged COSE_Sign1 checking under supplied public fixture key/kid and
expected payload is the implemented shared prerequisite. It returns a private signature
check result only; purpose, governance, threshold counting, currentness, readiness,
revocation application and registration remain outside that result's authority.
A valid wrong-purpose signature must demonstrate this distinction explicitly.
Existing threshold signature contexts are extracted without generating keys or
signatures; checking their signatures does not authenticate their fixture registry.

The local normal-revocation amendment now also composes the existing signed log,
consistency and authenticated witness verifiers against the record's checkpoint
reference. See `2026-10-11-normal-revocation-witness-integration.md`. This replaces
no governing policy and adds no universal witness round. It proves checkpoint
confirmation under fixture configuration, not record inclusion or durable restart.

## Local mapping implemented; runtime gates remain

The existing global-trust-v1 3/5 policy allows FederationTrustBundle replacement,
not TypedRevocationRecord normal termination. Do not reuse it merely because M/N
matches. The separately approved revision-2 mapping is now implemented in the
versioned local conformance amendment; see
`2026-10-11-normal-revocation-conformance.md`. Explicit eligible IDs and fixture
governing/control/witness inputs do not establish real accepted-context provenance.
Reconcile runtime activation authority for the retained Option C definition and
resolve real trust/freshness delivery, applicable witnesses and restart floors
before runtime eligibility. There is no controller fallback.

The approved inclusion persistence contract now has a storage-neutral codec and
coordinator tested with a memory backend. See
`2026-10-11-inclusion-persistence-implementation.md` for evidence. This strengthens
local recovery/replay semantics only. The subsequently authorized exact-root
filesystem trial passed real private writes, ACL observations, reopen and repair
after an injected completed-watermark replacement failure; see
`2026-10-11-inclusion-filesystem-matching-module.md`. This is a test harness, not
a production adapter. Process-death recovery, independent restart provenance,
power-loss durability and the runtime gates above remain unfulfilled. Stage 3
completion counts do not change.

The approved connected implementation is recorded in
`2026-10-11-connected-authority-owner-implementation.md`, following
`2026-10-11-connected-authority-owner-proposal.md`: native verified normal-event
application to the existing fixture-created destination owner under supplied test trust. Positive provider
admission and READY remain unavailable until all applicable governance paths are
implemented; this proposal grants no runtime activation.

## Isolated genesis KAR prerequisite

The separately approved genesis-only native gate now checks exact signature and
payload, explicit purpose and child identity, root-authorizer binding, active
unrevoked state and inclusive validity. It rejects non-genesis lineage and has
no authority, owner or readiness conversion. See
`2026-10-11-kar-genesis-implementation.md` for the bounded evidence.
Semantic acceptance/boundaries and composed signed rejection are covered
separately. **Successful composed positive acceptance is incomplete** under the
no-new-signatures constraint. No normal-roster assertion is replaced; five
purpose-12 authorizations/root mappings, real provenance, current governance,
rotation/recovery and runtime acceptance remain open. No stage count advances.
