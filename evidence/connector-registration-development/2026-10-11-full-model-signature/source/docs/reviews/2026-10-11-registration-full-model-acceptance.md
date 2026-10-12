# Full-model registration acceptance matrix

Status: required obligations, not runtime acceptance. Controller-only fallback is
superseded after the 2026-10-11 pause and independent security review. Stage 3 is
partial. No registry flag, source overlay or threshold byte definition is changed.

| Obligation | Required acceptance / negative case | Existing anchor and remaining gap |
|---|---|---|
| Target controller | Exact independently configured controller/operator for typed target; unrelated valid signer cannot act | revocation.py authorize mode 1; actual controller mapping/provider provenance absent |
| Normal 3/5 | Distinct eligible authorities and organizations, exact governing policy and all bound context; 2/5 or a controller cannot substitute | semantic mode 2 exists; no named normal TypedRevocationRecord 3/5 policy in current container proposal. global-trust-v1 applies to FederationTrustBundle/replace, not revocation |
| Emergency 2/5 | Exact authenticated quorum; nonterminal DENY_NEW_USE only, duration <=300 seconds; reject grant/restore/termination | typed-record validator + deny-only-emergency-v1 literal fixtures; producer/runtime composition absent |
| Every dependency | Authenticated governing profile, scope, complete closure and current revision; local profile selection cannot erase obligations | connector profile 919-935; runtime governance resolver absent |
| Signer purpose | KAR signed by IDENTITY_ROOT; authorized transport key purpose14 separate. Other signatures need exact applicable purpose | federation/cose.py; raw cryptographic success must never itself become authority |
| Forged/unsupported inputs | Invalid bytes/signatures or unrelated claims cannot mutate readiness. Independently proved freshness loss is separate; valid applicable termination must be enforced | new native primitive has no readiness/owner access; full dispatcher remains absent |
| Replay/restart | Exact request/session/counter plus authenticated non-regressing lineage/denial floors; old signed bootstrap cannot restore authority | offline counters/receipt checks exist; durable/current bootstrap provenance unresolved |
| Uncertain time | Expiry latest plausible UTC; event effective_at earliest plausible UTC; monotonic progress, invalid clock latch, no early termination | injected timer fixtures only; real-clock policy/source unresolved |
| Queue/effective revision | Future enqueue changes no eligibility; unrelated queue mutation cannot stale an applicable event | design constraint; real producer/dispatcher absent |
| Retention/capacity | Bounded pending state; no tombstone eviction/resurrection, no arbitrary service-lifetime event cap; failure retains quota | 64 is only optional test-inventory guard; service compaction unresolved |
| Active work | Admission expiry != ongoing expiry; deny-new preserves independently bounded work; applicable termination overrides grace; repeated drain cannot restart grace | connector model/timer tests; no live download acceptance |
| Cleanup | Failed/unconfirmed close retains ownership, exact confirmation needed, no premature replacement | existing Go/Rust cleanup tests; no new live shutdown proof |
| Threshold container | Exact existing Option C, protected headers, policy/group/scope/lineage/action/profile/capability/session binding; no substituted bare Sign1 list | retained supplement, allocation and 89 literal fixtures; runtime authority provenance unresolved |
| Runtime guard | No component result can admit registration until all applicable modes authenticated/enforced; no narrower operational fallback | new primitive cfg(test), integration-test target only, no Authority implementation or receipt/event constructor |

## Implemented slice and its limits

Native exact tagged COSE_Sign1 checking under supplied public fixture key/kid and
expected payload is the implemented shared prerequisite. It returns a private signature
check result only; purpose, governance, threshold counting, currentness, readiness,
revocation application and registration remain outside that result's authority.
A valid wrong-purpose signature must demonstrate this distinction explicitly.
Existing threshold signature contexts are extracted without generating keys or
signatures; checking their signatures does not authenticate their fixture registry.

## Exact missing choice

The existing global-trust-v1 3/5 policy allows FederationTrustBundle replacement,
not TypedRevocationRecord normal termination. Do not reuse it merely because M/N
matches. Resolve the approved normal-revocation named-policy mapping (including
class/purpose/diversity/effects/context), and reconcile runtime activation authority
for the retained Option C definition. Recommendation: preserve mode 2 semantics,
keep activation blocked, and seek that precise approved mapping rather than invent
one or fall back to a controller. Real trust/freshness delivery and restart floors
must also be resolved before runtime eligibility.
