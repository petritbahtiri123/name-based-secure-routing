<!-- Publication derivative; original SHA-256 06eb3bbec7ae377418e0eebb587c26048a902e0ba0765e4a1d4a849c6e2ceeb4. Personal attribution replaced by role label. Historical approval and result claims refer to the original local artifact, not a new action. -->

# Decision proposal: detached inclusion evidence for an immutable revocation

Decision `REVOCATION-INCLUSION-01`, revision 1: subsequently approved by project owner for
the bounded local conformance amendment only. See `2026-10-11-revocation-inclusion-v2.md`.
The design and review below are retained; no runtime activation permission follows.
The earlier JSON metadata is a historical pre-approval design snapshot.

## Existing definitions and the cycle

The development profile fixes leaf hashing as `SHA256(0x00 || canonical_leaf)`
and node hashing as `SHA256(0x01 || left || right)`. The schema's closed
TransparencyReference contains log ID, checkpoint digest, tree size and nullable
inclusion-proof digest. TypedRevocationRecord requires that reference at key 39.
The record digest is SHA256 of its entire deterministic CBOR payload. Option C
signatures bind that exact payload digest plus policy, group, scope, lineage,
action, request/event ID, validity, capability and session. InclusionProof already
binds log, scope, checkpoint digest, tree size, leaf index/digest/path and object class.
WitnessStatement binds the checkpoint root/digest/size and replay context.

Sources: `federation-v0.1-development-profile.md` cryptographic freeze gate;
`registries/federation-v0.1-schema-proposal.json` and schema-allocation;
`wp8-federation-v0.1-threshold-container.md`; `nbsr/federation/fields.py`,
`transparency.py` and `cose.py`. These definitions are reused, not rewritten.

Tiny example: let `R={decision: revoke, checkpoint: H(C)}`. A one-leaf checkpoint
`C={size:1, root:H(0x00 || CBOR(R))}` depends on R, while R depends on C.
Changing the checkpoint reference changes R and its signature digest, hence the
root and checkpoint digest again. Embedding `H(inclusion_proof)` adds another
cycle. The diagnostic in `2026-10-11-normal-revocation-inclusion-contract-gap.md`
demonstrates this ordinary construction problem; it does not prove that hash
fixed points cannot exist.

## Alternatives

| Approach | What is authenticated | Change and tradeoff |
|---|---|---|
| **A — immutable full record plus detached inclusion evidence (recommended)** | Authority signs full record including a prior checkpoint anchor. Log signs a later containing checkpoint and inclusion proof; witnesses confirm that checkpoint. Merkle membership binds the exact authority-signed record bytes. | Explicitly version key-39 semantics as a prior anchor; place later proof/checkpoint outside the record. Reuses all existing hash/signature/proof primitives and full-record digest. |
| B — canonical signed payload commitment | Define a new domain-separated commitment to an exact content projection, sign that commitment, log it, then authenticate all excluded checkpoint/proof information in an additional signed object. | Requires a new projection, commitment schema/domain, and additional signature/context rules. Merely dropping key 39 from a hash is unsafe and not this option. Creates more identities and verification paths than A. |
| C — retain key 39 as a containing-checkpoint reference in the signed record | Would need a specified pre-record or two-stage signing/commitment format to construct that reference. | Full final-record inclusion still cycles. A placeholder or mutable unsigned reference is not a solution. This collapses into a more disruptive version of B. |

Recommendation A preserves every authority-signed field and the meaning of the
whole-record digest. A prior anchor is a lower bound, never a claim of inclusion
or proof of currentness. The semantic change is explicit and opt-in, not an
interpretation applied to historical version-1 records.

## Exact proposed mapping

Provisional local profile selector: `nbsr-federation-revocation-inclusion-dev-v1`.
It is not a new globally allocated capability/action. An explicit approved profile
binding is mandatory; capability 6 alone cannot imply support. Unknown profile or
record version rejects without fallback. Future transport negotiation is outside
this local approval and remains blocked until specified/authorized.

**Record R:** deterministic CBOR TypedRevocationRecord, object class 13, proposed
object version **2** at key 2. Preserve all other fields, typed enforcement, signed
authority-mode selection, target/scope, validity and lineage. Key 39 is now the
explicit prior checkpoint anchor `{1: log_id, 2: H(A), 3: A.tree_size, 4: null}`.
A is an already accepted, authenticated checkpoint of the same log and scope.
Non-null key 39/4 rejects in this new version; it is not silently discarded.
It identifies no proof of R. Historical version-1 records keep their old contract.
The initial anchor may be an explicitly configured authenticated genesis checkpoint;
an absent anchor is not synthesized. Its current acceptance/floor provenance is a
separate prerequisite, not conveyed by its signature alone.

**Authority-signed bytes:** reuse Option C's complete existing signature-context
layout/domain and COSE Sign1 encoding. The target digest is exactly `SHA256(R)`;
profile context is the new explicitly selected profile; object class remains 13.
No authority field is excluded. Mode 2 uses approved normal-revocation-v1 3/5;
controller/emergency modes retain their distinct required authorities and typed
restrictions, with no substitution or new quorum. Initial implementation approval
may cover normal-mode conformance only; that does not permit normal-only runtime.
This first package/profile is normal-mode conformance only: modes 1 and 3 reject
as outside its scope, rather than being reinterpreted as normal. It allocates no
new controller packaging and does not weaken their separate runtime obligations.
The profile amendment must expressly bind this profile and record version 2 to
the named policy. Existing verifier profile/version accept-lists are not extended
by this proposal itself.

**Leaf bytes:** exactly R, including version, prior anchor, optional extensions
and every signature-covered field. `leaf_digest = SHA256(0x00 || R)` with the
existing leaf domain. There is no new leaf projection, placeholder or extra hash
domain. `SHA256(R)` remains the record identity; the leaf-domain hash remains
separate. The existing Option C signature domain and signed profile distinguish
the new authority context. The log contains the canonical payload, not a mutable
collection of threshold signatures.

**Detached evidence package:** proposed deterministic CBOR closed map, local-only
package version 1, with exact fields below. It is an evidence container, not a new
authority grant. No collector signature is required: every security-relevant item
is independently authenticated and cross-bound. Collector-controlled metadata
must never select the governing policy, roster, log, threshold or replay context.

| Key | Proposed value |
|---:|---|
| 1 | package version uint 1 |
| 2 | exact proposed profile selector text |
| 3 | R as canonical payload bstr |
| 4 | canonical Option C threshold envelope bstr authenticating SHA256(R) |
| 5 | log COSE Sign1 containing checkpoint C |
| 6 | log COSE Sign1 containing InclusionProof P |
| 7 | log COSE Sign1 containing ConsistencyProof from A to C |
| 8 | array of witness COSE Sign1 messages, canonical signer order; trusted signer metadata comes from accepted configuration |
| 9 | log COSE Sign1 containing anchor checkpoint A |

All artifact bodies retain existing schemas and exact-purpose checks. P binds
object_class exactly 13 (null is not sufficient here), log/scope equal R/A/C,
checkpoint_digest `SHA256(C.payload)`, C's tree size, and `SHA256(0x00 || R)`.
C has tree size strictly greater than A and the inclusion index is at least
A.tree_size, proving this record's placement after the anchor. To keep the first
local slice bounded, require C to be the immediate accepted checkpoint successor
of A under existing TransparencyVerifier continuity. Skipped checkpoint chains,
key rotation and cross-log migration are outside this first conformance profile;
they must not trigger fallback. This restriction is proposed conformance scope,
not a claimed universal requirement of Merkle inclusion.

The consistency proof binds exact A/C digests, sizes and roots. C must be fresh
on every use; authenticated witnesses bind exact C and accepted per-witness replay
contexts under the independently determined applicable policy. Package key 9 must
match the already accepted anchor identity/floor, not become a newly trusted anchor
merely because the collector supplied a valid old signature.

For this immediate-successor local scope, let F be the independently retained
current checkpoint floor for the log/scope. Permit exactly F=A for a first forward
check, or F=C with the identical checkpoint digest for evidence re-use. Reject a
different digest at the same floor and any package with C below F. Other floor/
chain relationships are unsupported in this first slice, not repaired by replacing
F with package A. Reusing evidence at F=C still checks current validity, witnesses,
replay and revocation-record lineage, and creates no second authority mutation.
Rejecting an old evidence package never removes an already applied denial. A later
containing checkpoint C-prime cannot refresh this same R in the immediate-successor
slice; broader historical-anchor/proof-chain support needs a separate explicit mapping.

The first local fixtures cover contexts already requiring the existing 2/3 or 3/5
witness policies. They add no universal witness requirement to normal revocation.
Other governing-policy contexts need their own explicit coverage; an empty witness
array cannot be used as a local decision that witnesses are unnecessary.

Proposed package bound: 65,536 encoded bytes, no compression or external references;
retain existing per-artifact canonical/payload/path/signature limits, maximum five
witnesses and normal five eligible authority entries. Reject an oversized package,
never truncate evidence or lower a threshold. Validate these bounds with literal
fixtures before any subsequent implementation recommendation. No automatic splitting
or new fragmentation protocol is authorized.

## Verification, replay and compatibility

Validate the selected package/profile/version and bounds before cryptography.
Obtain governing configuration, current floors, expected request/session context
and applicable witness obligations independently of the package. Verify authority
signatures against full R and exact selected mode, then log/proof/witness signatures
and all cross-bindings, consistency, inclusion, freshness and lineage/replay floors.
Only after **all** checks succeed may a future authorized runtime atomically retain
required floors/denials and apply exact typed enforcement. This proposal constructs
no receipt or runtime authority and specifies no unapproved persistence mechanism.
Malformed/untrusted claims cannot mutate readiness; independently established
freshness loss remains a distinct authority fact.

The Merkle proof is reusable evidence, not a fresh authorization. Replaying a
package cannot refresh record validity, restart a grace period, clear a tombstone,
advance a floor twice or bypass request/session checks. Equal record version and
digest follows existing idempotence; different digest at equal lineage is equivocation;
older lineage rejects. A new action/session needs its own valid Option C context.
Log signatures, witness signatures and proof membership do not replace this.

The package itself is not the revocation identity. Equivalent independently valid
proofs of the same R are acceptable only when every selected checkpoint, scope,
floor, freshness and replay constraint still passes; changing collector packaging
does not create a new event. There is deliberately no circular record commitment
to one particular future proof encoding.

Substitution tests must cover record bytes, target, mode, scope, anchor, object class,
profile/version, root/checkpoint digest, proof digest/path/index, witness context,
wrong-purpose keys and wrong governing roster. Verify no mutation after every failure
and crash-safe floor/application behavior separately when persistence is approved.

Historical version-1 records, the existing 89 threshold literals, normal-conformance
33-case package and all registry/source pins remain unchanged. Add a separately
versioned amendment and new fixtures only. Do not re-sign or migrate old identities
in place, reuse an old profile's meaning, or claim old parsers accept version 2.
Rejection by old implementations is intended compatibility behavior, not grounds
for a downgrade. The prior witness composition remains a historical checkpoint-
confirmation test, not retroactively an inclusion proof.

## Approval requested

Approve decision REVOCATION-INCLUSION-01 **only for versioned local conformance**:
option A; full canonical version-2 record as leaf; key 39 as an authenticated prior
anchor with null proof reference; separately authenticated later checkpoint,
inclusion/consistency/witness evidence package; exact new profile binding and the
bounded immediate-successor test scope above. This is one semantic/package decision,
not approval to change existing registries or deploy a trust producer.

After approval: deterministic public-material vectors, negative binding/replay/
mutation tests, existing verifier composition and independent security review.
Real governing provisioning/currentness, durable restart floors, all-mode runtime
composition and final comprehensive audit remain separate gates. Runtime/live flags
stay false. No keys, network tests, verifier/wire changes, commits or push in this
design task.

## Independent review disposition

The independent scoped reviewer found no remaining blocking design issue after
clarifying the distinct prior anchor A and retained floor F with the exact F=A /
F=C rule. The reviewer confirmed that full R remains signature-covered, later
evidence is cross-bound, and normal-only local conformance does not authorize a
narrower runtime. The review specifically retained the limitation that a later
floor can make this bounded package unusable without undoing an applied denial.
Broader proof-chain renewal remains outside scope. Review was read-only, with no
tests; this is clearance to present the proposal, not approval to implement it.
