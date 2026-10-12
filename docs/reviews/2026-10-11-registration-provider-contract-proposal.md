# Registration provider: full security model, corrected decision

Status: local work resumed on the full accepted security model, 2026-10-11.
Controller-only operation is superseded, not a supported fallback. Runtime
activation and registry runtime/live-trust flags remain unchanged and false.

## Pause and independent review

The user paused the earlier controller-only proposal before any implementation.
Only this proposal and the plan had been edited. Independent security review found
that one operator does not imply controller-only governance: refusing a valid
normal 3/5 termination while only withdrawing new use leaves affected active work
running. A local profile switch cannot remove inherited dependency obligations.
Earlier review of scheduling ambiguities did not establish security equivalence.
The earlier proposal JSON records a historical document hash, not this revision.

Other findings: untrusted bytes claiming a dependency cannot disable readiness;
valid signatures and finite expiry do not prove currentness or safe restart;
KAR signing requires IDENTITY_ROOT while purpose 14 describes the authorized
transport key; emergency authority is not permission for active-use termination.

## Required model

Authenticate the complete governing context and every dependency before admitting
registration. Enforce target-controller authority, normal 3/5 and emergency 2/5
where applicable, without mode substitution or threshold downgrade. Emergency is
nonterminal DENY_NEW_USE for at most 300 seconds. Controller/normal enforcement
remains exactly that authorized by the typed record. Preserve purpose, scope,
lineage, organization diversity, named-policy and capability/session bindings.

Private signature results alone are not authority, registration receipts or commit
permits. A future permit must bind exact peer, service/operator/gateway, connection,
session, request counter/digest, current dependency governance, authority revision,
categorized deadlines and verified provenance. Serialize final checking and commit.
No malformed, unsupported or unauthenticated input may manufacture a revocation
or change readiness merely by naming an owner. Independently established loss of
freshness withdraws new use; applicable authenticated termination must be enforced.

## Trust, time, retention and existing work

Reuse existing trust_ref/registration_policy_ref/registration_authority_ref names.
A future resolver must provide authenticated signer/governance state, complete
record/dependency inventory and non-regressing denial/lineage floors. Current
public deterministic fixtures are explicit test inputs only. They establish no
real provisioning, revocation completeness or freshness. Restart must not restore
registration or allow a stale signed snapshot to resurrect authority.

Use injected bounded clocks for tests. One second is not a measured host guarantee.
Check expiry against latest plausible UTC; dispatch future enforcement only when
earliest plausible UTC reaches effective_at. Preserve monotonic progress and
invalid-clock latches. Future enqueue does not change effective authority revision;
unrelated queue changes do not silently discard applicable events.

64 entries is at most a test-inventory guard, never a service-lifetime event cap.
Runtime pending-work bounds and safe replay/tombstone compaction remain unresolved.
Overflow cannot claim enforcement, discard safety state or release owned quota.
Registration/admission expiry is distinct from ongoing authority and profile-bound
drain. Deny-new preserves independently valid bounded work; applicable termination
overrides grace. Failed cleanup retains visible ownership. No arbitrary transfer
limit or continuity guarantee is introduced.

## Implemented local prerequisite

Implemented a test-only native tagged COSE_Sign1 signature boundary using the existing
Ed25519 dependency, exact protected-header rules and retained public signed vectors.
Require exact expected payload/kid and public key. Signer purpose, lifecycle,
validity and provenance must be checked by the future authority layer; this
primitive checks none of those. Its private result proves only the bounded
cryptographic check under supplied fixture inputs. It cannot construct a registration receipt/event,
implement Authority, change readiness, or activate any mode. Exercise the same
primitive on existing threshold Sign1 contexts without inventing container bytes.

This is a shared prerequisite for all authority modes, not a controller provider.
No source-authority overlay or registry changes are required for this test-only
module. The acceptance matrix in
2026-10-11-registration-full-model-acceptance.md tracks remaining obligations.

## Exact unresolved gates and recommendation

Existing Option C bytes/capability allocation and literal vectors must be reused.
History includes freeze/allocation commits, while supplement headings still say
proposed and SemanticThresholdEvidence.from_transport rejects packaging. Resolve
which versioned definition has runtime authority and the exact TypedRevocationRecord
normal-3/5 policy mapping before any producer can issue live authority. The latter
now has an approved separate local conformance amendment documented in
`2026-10-11-normal-revocation-conformance.md`; this does not grant runtime authority. Do not infer
runtime approval from commit titles or invent a substitute policy/container.

Real trust provisioning/freshness delivery, durable rollback-resistant restart
floors, real clock policy and all-mode runtime composition remain separate gates.
Recommendation: retain complete governance requirements and keep registration
unavailable until all applicable modes are authenticated and enforced. Test isolated
primitives and conformance now; do not offer a narrower operational fallback.
Stage 3 remains partial. Final comprehensive security audit before a real pilot
is required in the implementation plan; focused security review continues now.
