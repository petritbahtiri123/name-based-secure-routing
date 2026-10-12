<!-- Publication derivative; original SHA-256 576af1bd40038464c5b31d08addf21fad2b19a3da3e2f211851a6f5a4bdc46f8. Personal attribution replaced by role label. Historical approval and result claims refer to the original local artifact, not a new action. -->

# Final recommendation: minimal faithful mapping (revision 2)

This section supersedes revision 1's recommended additional organization roster,
membership-witness infrastructure and event-timing choices below. Revision 1 is
retained as a historical optional-hardening proposal, not the recommended default.
Status: project owner subsequently approved revision 2 for separate versioned local
conformance implementation only. See `2026-10-11-normal-revocation-conformance.md`.
Runtime activation remains unapproved; revision 1 below remains historical.

Recommend a dedicated normal-revocation-v1 policy, version 1, with one group
normal-revocation: signed mode 2, object 13, authority class 4, purpose 12, 3-of-5,
REVOCATION_PUSH 16407, effect deny, no authority expansion. Preserve exact typed
normal enforcement; do not impose emergency's deny-new-only/300-second constraint.
Keep Option C's existing schema, digest derivation and complete context bindings.

Use the existing authenticated governing membership/context and eligibility rules.
Five eligible authorities and the counted quorum must meet the inherited genuine
organizational/operational independence requirements. Multiple keys, authority IDs
or nominal companies under material common control cannot count independently.
Do not add a new requirement for five separately incorporated organizations or a
normal-mode three-stakeholder-class rule. Map trusted control identities into the
existing minimum_organizations=3 descriptor constraint without treating names or
self-declarations as evidence of independence. Eligible IDs may be explicit or use
the existing accepted-context lookup, with exactly five scope/policy-authorized
eligible identities and no signer-selected roster or automatic denominator shrink.

Reuse all applicable existing transparency/witness requirements. Add neither a
universal 2-of-3 membership-checkpoint prerequisite nor permission to skip a fresh
per-event witness round. The existing governing policy decides those obligations;
unknown or unsatisfied requirements leave runtime eligibility unavailable. A
witnessed snapshot cannot substitute for freshness, current revocation or rollback
floors. Missing provenance is an implementation/activation gap, not authorization
to invent a new trust service or treat a fixture as current authority.

The ratified normal signer matrix contains one 3/5 REVOCATION signer set and no
additional witness set. Mandatory witnesses elsewhere must be retained where
applicable: F118 specifies 2/3 matching witnesses for global/high-impact transparency
partitions; ordinary registry issuance includes 2/3 witness confirmation; root
bundle transitions and operator-wide recovery have stronger context-specific
requirements. Those are not proof of a universal extra membership-witness round
for every routine normal revocation. High-impact acts cannot be relabelled routine
to avoid their stronger registry/governance/transparency obligations.

| Choice | Threat / existing control | Minimal faithful mapping | Optional stronger revision-1 choice |
|---|---|---|---|
| Independence | Common-control signers fake quorum. F118 already counts shared control as one; Option C counts trusted organization identities. | Enforce inherited independence and counted diversity; no new corporate-form requirement. | Five explicitly distinct organizations as a separately chosen operational restriction; not automatically stronger if common control remains. |
| Membership witnesses | Publisher equivocation or substituted membership. Existing authenticated governance, lineage, accepted context and applicable transparency rules address this. | Reuse those controls; unavailable until real provenance/currentness exists. | Additional 2/3 witnessed membership checkpoint only if a specific uncovered threat justifies cost; representation must already be approved or separately decided. |
| Event witness timing | Waiting can delay containment; skipping required witnesses can admit insufficiently authorized action. Existing event/governance policy determines acceptance. | Preserve that policy, with no new timing exception or universal wait. | A changed timing policy needs explicit impact analysis and approval; revision 1's no-new-round choice is not recommended by default. |

Exact decision requested: approve the missing named-policy/group mapping and its
binding to existing normal mode, independence, accepted membership context and
applicable transparency rules, for versioned local conformance work only. Do not
reapprove the inherited 3/5 semantics, add optional barriers, or declare absent
provenance solved. Before runtime, resolve the exact accepted membership source and
its governing transparency/freshness/rollback requirements; if historical authority
for those is missing, present that narrow missing choice. No fallback or activation.

---

# Proposed normal-revocation Option C mapping

Decision candidate: NORMAL-REVOCATION-OPTION-C-01, revision 1.
Status: DESIGN ONLY; requires user approval. No policy entries, wire bytes,
registry activation, keys or runtime behavior are created by this document.
Assistant-authored historical APPROVED labels are not independent human approval.

## Inherited semantic authority

The ratified development registry, signer_authority_matrix/TypedRevocationRecord,
selects exactly one alternative using the signed revocation_authority_mode.
Normal is mode 2, object 13, FEDERATION_AUTHORITY class 4, REVOCATION purpose 12,
3 of 5. This is present in ratification commit 4c8c9ef9 and threshold commits
149623a8/0849b986. Controller mode 1 and emergency mode 3 are distinct alternatives,
not fallback quorums. Unknown modes reject without mutation.

F118 requires genuine organizational/operational independence. Its explicit three-
stakeholder-class requirement describes global trust; this proposal does not silently
apply that exact rule to every normal revocation. Stronger applicable governance,
registry, witness, transparency and high-impact requirements remain binding.

## Exact proposed descriptor

These names and the concrete container mapping are NEW proposals, not discovered
allocations. Retain existing Option C schema/container version and capability 6.

| Field | Proposed value |
|---|---|
| policy_version | 1 |
| policy_name | normal-revocation-v1 |
| allowed_object_classes | [13] (TypedRevocationRecord) |
| allowed_message_types | [16407] (REVOCATION_PUSH) |
| allowed_authority_effects | [deny] |
| deny_only | true: prohibits adding/restoring/expanding authority; not an enforcement-mode alias |
| group_requirements | exactly one group, in this order: normal-revocation |
| group required/eligible | 3 / 5 |
| eligible_authority_classes | [4] |
| required_class_counts | [[4,3]] |
| allowed_key_purposes | [12] |
| group deny_only | true, same non-expansion meaning |
| minimum_organizations | 3, counted from trusted control relationships |
| eligible_authority_ids | exact five authenticated, sorted unique identities; no empty context-lookup shortcut for this version |
| scope_digest | exact canonical governing scope under existing target/scope rules |
| extensions | none in this initial mapping |

policy_id is the existing SHA-256 derivation over deterministic CBOR of the
complete descriptor with its key 2 null, then substituted at key 2. No digest is
published now: actual approved membership and scope are unavailable. Membership
or scope changes produce a different digest. The verifier matches the complete
approved template AND independently authorized roster/scope; a self-consistent
policy digest or recognized name cannot authorize a signer-selected roster.

Use the existing signature domain and all twelve context bindings: object/digest,
policy/group, scope, lineage, action/event ID, validity, profile, capability and
authenticated session. Bind exact mode 2 by validating the signed target payload.
No grant/replace/recover/decide operation, message substitution or scope expansion.

The boolean deny_only does NOT impose emergency's nonterminal DENY_NEW_USE or
300-second limit on normal mode. Preserve typed NONE/DENY_NEW_USE/REAUTHENTICATE/
DRAIN/TERMINATE_ACTIVE_USE meaning exactly under the governing policy; it cannot
invent permission for any mode. Terminal records retain MAX_TIME expiry and
non-resurrection rules. Normal mode does not grant recovery or clear tombstones.

## Membership provenance and independence: new concrete constraints

Use an explicitly authenticated, scope-bound, versioned membership snapshot from
the existing configured federation governance context, never the incoming envelope
or transport peer's claims. It must identify exactly five eligible authorities,
exact authorized purpose-12 keys/kids, active lifecycle, validity, lineage and
current revocation state, plus trusted organizational/control-domain relationships.
Require five independently controlled organizations in the eligible roster and at
least three in the counted quorum. Three companies under one administrator, parent,
beneficial owner or material common command path count as one. Three stakeholder
classes are not newly imposed for routine scope; any stronger applicable rule is
still mandatory. Cryptographic key diversity does not establish independence.

This numerical normal-mode diversity/roster choice is a conservative NEW profile
proposal. It reduces common-control capture but raises membership/provisioning and
availability costs. No identities, keys, independence claims or membership source
are invented here. Missing provenance, ambiguous shared control, stale/unknown
freshness or missing anti-rollback floors leaves the verifier unavailable. No
shrinking denominator, automatic replacement, self-authorized membership rotation,
TOFU or fallback. Membership changes need the separately applicable authorized
governance process and a new descriptor; this deny-only policy cannot approve them.

## Witness recommendation: separate membership and event obligations

NEW recommendation: before the membership snapshot is eligible for use, require
an authenticated inclusion/consistency chain to its exact accepted checkpoint and
ordinary 2-of-3 witness confirmation of that SAME checkpoint. Use existing checkpoint,
proof and witness types; do not invent a membership wire format or reinterpret the
revocation's key-39 transparency reference as membership proof. The three witness
identities and their purpose-9 keys must come from independently configured trusted
witness governance, not the membership snapshot being vouched for. Require independent
control among witnesses and from the publishing log; for this conservative proposal,
also separate their controlling organizations from the five revocation authorities.

The exact checkpoint must commit the exact membership-snapshot digest and scope/
revision being supplied as accepted_authority_registry context. If no existing
approved representation can establish that binding, remain unavailable; this
proposal does not invent one. Witness signatures do not replace any of the three
revocation-authority signatures. They do not prove that the snapshot is still
current: freshness, later signer revocation and rollback floors remain separate.

NEW explicit enforcement-timing choice: for routine normal revocations, do not
require a NEW per-event witness round merely because this mapping is selected,
provided current witnessed membership is established and ALL independently applicable
record-level transparency/witness obligations are already satisfied. Membership
confirmation is not event confirmation. If event-level policy is missing/ambiguous
or requires further evidence, remain pending/unavailable under that policy rather
than assuming authorization. This timing choice itself requires user approval.

This avoids adding witnesses to the ratified 3/5 authority group and avoids delaying
a valid effective routine denial for a redundant round. It trades a stronger,
less available membership-update gate (potentially eight independent organizations)
for faster enforcement under already trusted membership. No arbitrary 60-second
normal confirmation timer is proposed. Missing evidence cannot undo an already
valid terminal denial or authorize restored/new use.

## Target impact and alternative separation

Eligibility for this routine mapping must be established from authenticated
preexisting governance, exact target/dependencies and action impact, not a sender's
routine label. Operator-ID terminal revocation, global/root/governance/threshold
change, recovery or other F118 high-impact acts cannot be authorized by this
routine mapping alone. Where stronger policies are required, require their exact
approved evidence and path; absent that path reject as unsupported. Do not invent
those policies, flatten their groups, or relabel the act as operational revocation.
This restriction is a conservative new applicability rule, not proof all target
classes already have resolved runtime governance.

Controller signatures cannot satisfy mode 2 or replace missing members. A signed
mode-2 object cannot be interpreted as mode 1 or 3 when quorum fails. A separate,
properly authorized emergency object remains mode 3, 2/5, nonterminal DENY_NEW_USE,
maximum 300 seconds; it cannot terminate active use or make the normal object valid.
No controller-only runtime profile is reintroduced.

## Vectors and acceptance to add only after approval

Positive: exactly three and over-threshold four/five distinct eligible signers;
correct full context, scope/membership policy digest and witnessed membership;
normal deny-new and authorized termination/drain/reauthentication cases kept
separate; future-effective event remains inactive until due; exact duplicate
idempotence; terminal denial retained across explicitly verified restart floors.

Negative: two-of-five; duplicate IDs/keys; same-controller organizations; ambiguous
kid/key ownership; wrong class/purpose/lifecycle; stale or revoked signer; fabricated
or old witnessed membership; wrong checkpoint/inclusion/consistency/witness scope;
signer-selected roster/policy; membership from another service/profile; altered
mode/policy/group/action/event/session/capability/lineage; invalid extra signature
even above quorum; global-trust-v1 substitution; controller/emergency substitution;
3/5 routine packaging for high-impact acts without stronger governance; missing
required per-event evidence; clock uncertainty causing early termination; malformed
claims causing readiness mutation; repeated drain reset; cleanup failure releasing
quota; expired cache or restart restoring revoked authority.

Use existing public deterministic fixture keys only under separately approved
vector-generation scope. Test Python/native verification and existing semantic
oracles separately; crypto success is not purpose, quorum, currentness or runtime
acceptance. Container rejection/pending remains mutation=false. A full registration
runtime remains unavailable until every applicable authority mode is implemented
and its real governance/currentness/enforcement path passes acceptance.

## Proposed narrowly bounded approval wording

Approve NORMAL-REVOCATION-OPTION-C-01 revision 1 as a local development design,
including the new explicit roster/diversity, witnessed-membership and routine-event
timing/applicability choices above. Authorize a separately versioned, test-only
machine-readable amendment, literal positive/negative fixtures using existing
public deterministic test-key material, offline validation and independent security
review. Preserve historical definitions and thresholds; no membership identities,
real trust source or high-impact policy may be invented. If the membership-checkpoint
binding cannot be expressed by an existing approved representation, report that
precise gap before implementing that binding. This approval does not activate
runtime/live trust, install anything, create real/persistent keys, open sockets,
change production source pins or authorize publication/push.

## Sources and independent review

Sources: federation-v0.1-development-profile.md signer matrix; development registry
signer_authority_matrix/TypedRevocationRecord; schema RevocationAuthorityMode and
TypedRevocationRecord; historical F118/F93; Option C supplement and named-policy
registry. Parent ChatGPT-history search found no exact normal policy/group mapping;
assistant-written approval labels were not treated as user authority.

Independent security review rejected treating post-publication witness timing or
a 60-second deadline as inherited semantics. The revised recommendation removes
that timer, separates witnessed membership from event obligations, and expressly
requires approval for the no-new-per-event-round timing choice. Reviewer found no
remaining structural blocker to documenting that bounded proposal, while retaining
freshness/rollback and activation gates. This is not established full-security
or runtime equivalence. No code or tests were run for this design decision.
