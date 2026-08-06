# WP8 Federation decisions F1-F119 and corrections V1-V6

**Task 0 status:** Proposed for human approval. The F-number list is a canonical
condensed index and does not replace the unavailable full historical source.
Its detailed appendices, the Development Profile, direction document, and
machine registry are repository-accessible detailed normative supplements,
but they do not constitute the complete detailed source.
`WP8-NORMATIVE-SOURCE-01` is therefore blocking:
Task 1 remains blocked until either the exact digest-pinned historical source
is checked in immutably or this document is expanded and approved as a complete
detailed replacement for every F1-F119 and V1-V6 decision. Clean-room
implementation is not authorized while the blocker remains. No Federation
runtime or wire freeze is created.

## Identity and keys

**F1.** An Operator ID is a stable self-certifying identifier derived from an immutable genesis commitment.
**F2.** The Development Profile binary Operator ID is the 32-byte SHA-256 genesis commitment.
**F3.** Its text form is lowercase Bech32m with HRP `nbsr`; uppercase and mixed-case input fail.
**F4.** Public-style operation associates verified organization metadata without embedding it in the identifier.
**F5.** Private operators use the same cryptographic identity form without a public listing claim.
**F6.** Subsidiary identifiers are independently committed and explicitly linked; string hierarchy grants no authority.
**F7.** Retired and terminally revoked identifiers are never reused.
**F8.** Identity continuity is expressed by signed, generation-monotonic lifecycle records.
**F9.** The identity-root private key is offline except for genesis and expressly authorized root actions.
**F10.** Every operational key has exactly one registered purpose.
**F11.** The Development Profile accepts Ed25519 only.
**F12.** Operational keys carry bounded activation and expiry times.
**F13.** Rotation uses explicit `NEXT`, `ACTIVE`, `RETIRING`, `RETIRED`, and `REVOKED` states.
**F14.** Production custody and HSM requirements are deferred to a production profile.
**F15.** A Key Authorization Record is signed by the identity root or an authorized recovery path and binds operator, key ID, purpose, validity, lifecycle, generation, sequence, and predecessor.

## Ownership and delegation

**F16.** Name authority begins at a registry-rooted Name Ownership Record.
**F17.** Ownership records bind the owner, name scope, service scope, generation, sequence, and continuity digest.
**F18.** Delegation is owner-controlled and never inferred from delivery behavior.
**F19.** Delegation scope is the intersection of explicit name, service, tenant, region, protocol, port, and action constraints.
**F20.** A child delegation must be equal to or narrower than its parent.
**F21.** Sub-delegation requires an explicit permission bit and cannot broaden scope.
**F22.** Delegation chains are acyclic and bounded by the profile depth and object limits.
**F23.** Delegation validity cannot exceed parent validity.
**F24.** Revocation applies transitively to dependent delegated authority.
**F25.** Updates are generation/sequence monotonic and hash-linked.
**F26.** One authoritative owner may designate multiple explicitly scoped delivery operators.

## Registration, services, transfer, and recovery

**F27.** Operator and service onboarding use one closed registration flow.
**F28.** Existing Internet ownership evidence is bootstrap evidence, not perpetual Federation authority.
**F29.** A Service ID is stable across authorized delivery-operator changes.
**F30.** Multiple delivery operators require separate explicit scopes.
**F31.** Ownership transfer requires authorization from current and proposed owners.
**F32.** Transfer takes effect only after registry and transparency acceptance.
**F33.** Recovery cannot bypass ownership-transfer authority.
**F34.** Threshold recovery is restricted to the exact recovery scope and cannot add unrelated trust.

## Transparency

**F35.** Trust-critical Federation objects require transparency evidence.
**F36.** Private attributes appear only through profile-approved commitments.
**F37.** Logs are append-only Merkle structures with signed checkpoints.
**F38.** Inclusion proofs bind accepted objects to a checkpoint.
**F39.** Consistency proofs bind successive checkpoints.
**F40.** Witnesses sign checkpoint statements under a witness-only key purpose.
**F41.** Witness thresholds require organizational diversity.
**F42.** Gossip compares same-size checkpoints and retains conflicting branches.
**F43.** Same-size different-root evidence is a split view and causes quarantine.
**F44.** Conflict evidence is retained rather than resolved first-seen-wins.
**F45.** Private transparency domains are explicitly scoped and cannot claim public assurance.
**F46.** Privacy commitments do not weaken proof, freshness, or revocation requirements.

## Trust bundles

**F47.** Federation Trust Bundles are canonical, signed, and scope-bound.
**F48.** A bundle signer must hold the exact registered authority class and purpose.
**F49.** Bundle reconciliation is deterministic over generation, sequence, digest, and continuity.
**F50.** Hierarchical bundle composition is restrictive intersection only.
**F51.** Keys have explicit activation, overlap, retirement, and revocation state.
**F52.** Normal key overlap is bounded by the Development Profile.
**F53.** Bundle updates are generation/sequence monotonic and hash-linked.
**F54.** Lower versions are rollback and fail closed.
**F55.** Equal version/equal digest is idempotent acceptance without mutation.
**F56.** Equal version/different digest is equivocation and quarantines both branches.
**F57.** Checkpoint, trust, and cache freshness obey bounded clock skew and staleness.
**F58.** Emergency revocation is deny-only and cannot add or broaden authority.
**F59.** Recovery and high-risk root changes require their higher thresholds.
**F60.** Transparency and witness verification complete before bundle authority mutates.

## Discovery and authorization

**F61.** Federation discovery is part of the NBSR Name Plane.
**F62.** DNS, HTTPS, and static configuration provide candidates only.
**F63.** An endpoint is usable only after cryptographic operator and transport-key binding.
**F64.** Discovery cache entries are signed and freshness-bounded.
**F65.** Conflicting discovery sources reconcile by verified authority, not source priority.
**F66.** Bilateral mode requires exact preconfigured peer authorization.
**F67.** Private-consortium mode requires an explicitly scoped trust bundle.
**F68.** Discovery responses do not disclose Origin Endpoints to clients.
**F69.** Failure to verify discovery never triggers automatic static fallback.
**F70.** Authorization validates the complete ownership/delegation/registry authority chain.
**F71.** Source and destination operators authorize independently.
**F72.** Accepted checkpoints must be mutually compatible under the profile.
**F73.** Bilateral authorization binds exact source operator, destination operator, and service.
**F74.** Federation authorization is represented beside, and never inside, immutable RouteGrant.
**F75.** FederationAuthorizationContext binds the exact proofs, bundles, checkpoints, policy, and operators.
**F76.** Updates invalidate only grants and channels dependent on the changed authority.
**F77.** Authorization exposes the minimum information required for the decision.
**F78.** A missing or invalid destination decision cannot be replaced by source authority.

## Privacy and abuse

**F79.** Discovery is exact-match and anti-enumeration.
**F80.** Transparency commits private names and metadata using the frozen commitment profile.
**F81.** Delegation discovery does not reveal subscriber identity.
**F82.** Cross-operator subscriber references are scoped pseudonyms.
**F83.** Audit events contain only the minimum inter-operator evidence.
**F84.** Routine abuse evidence is session-unlinkable outside its scope.
**F85.** Identity escalation requires controlled, authorized evidence opening and an audit record.

## Revocation, lifecycle, and outage

**F86.** Revocations are typed by target object class and reason.
**F87.** Revocation reason determines restricted, drain, terminate, or terminal behavior.
**F88.** Terminal identifiers and terminal authority records create permanent tombstones.
**F89.** Last-known-good operation is bounded, explicitly restricted, and never applies to known compromise.
**F90.** The outage matrix states which evidence may be pending, restricted, or rejected.
**F91.** Enforcement severity is exactly `NONE`, `DENY_NEW_USE`, `REAUTHENTICATE`, `DRAIN`, or `TERMINATE_ACTIVE_USE`.
**F92.** Operator compromise can quarantine the complete operator scope.
**F93.** Recovery follows explicit stages, thresholds, continuity rules, and re-entry monitoring.
**F94.** Re-entry requires fresh accepted authority and never erases retained conflict or terminal evidence.

## Conformance

**F95.** Conformance is tiered into object, control-plane, shared-transport, and independent end-to-end claims.
**F96.** Python is the normative reference implementation after literal schemas and vectors exist.
**F97.** Go is a clean-room second implementation using repository-accessible normative inputs only.
**F98.** Deterministic vectors cover valid, invalid, boundary, and mutation cases.
**F99.** Stateful manifests contain literal expected outcomes before state-machine implementation.
**F100.** Outcomes, reasons, enforcement, state digest, mutation flag, and side effects are exact.
**F101.** Resource, timing, restart, compaction, and synchronization behavior is tested.
**F102.** Byte agreement alone supports only an object/vector claim.
**F103.** Independent end-to-end claims require two complete independent stacks and role reversal.

## Extension and compatibility

**F104.** Federation v0.1 is a separately versioned extension over required Core version 2.
**F105.** Federation uses dedicated extension-local object, semantic message,
result, reason, lifecycle, purpose, authority, and capability registries. The
exact Task 0 allocations and per-message behavior are authoritative only after
human approval; no target message count is normative.
**F106.** Federation object schemas are closed and reject unknown critical semantics.
**F107.** Unsupported critical capabilities fail closed.
**F108.** Static trust compatibility is an explicit separate profile.
**F109.** There is no automatic Federation-to-static downgrade.
**F110.** Federation does not allocate or reinterpret a Core message value.
**F111.** RouteGrant fields, wrappers, state transitions, and COSE semantics remain unchanged.

## Governance

**F112.** Production Federation governance requires multiple independent stakeholders.
**F113.** Production registry operation must be institutionally neutral.
**F114.** Registry lifecycle changes are signed, transparent, and verifiable.
**F115.** Conflicts are decided from retained evidence under explicit authority.
**F116.** Appeal is separate from recovery and cannot reactivate terminal authority.
**F117.** No single operator or sponsor controls every root, log, and witness.
**F118.** Authority and witness thresholds scale with action risk.
**F119.** Sponsor concentration limits and diversity rules are production-profile requirements.

## Validation corrections

**V1.** Resource and parsing safety precedes canonical, cryptographic, authority, state, freshness, and local-policy validation.
**V2.** A named validation correction overrides only the conflicting decision and never rewrites frozen Core history.
**V3.** Replay-state retention is at least 86,400 seconds in the Development Profile; terminal tombstones are permanent and non-expiring.
**V4.** Continuity-preserving recovery retains the genesis-derived Operator ID with a strictly higher identity generation; lineage-breaking recovery terminally tombstones the old Operator ID and requires a new genesis-derived Operator ID.
**V5.** Registry and schema literal vectors precede codecs; literal stateful scenario manifests precede the Python state machine; generated package completion follows reference implementation.
**V6.** Task 0 values remain proposed for human approval; approval creates Development Profile authority, while permanent wire freeze and production-profile values remain later decisions.

## Task 0 claim boundary

Task 0 prepares repository-complete planning authority. No federation runtime is implemented by Task 0. It is not a permanently frozen Federation wire allocation and provides no live federation, public governance, independent interoperability, origin anonymity, DDoS elimination, complete partition tolerance, or production readiness.

## Detailed F105 message semantics

Capability agreement is `FED_CAPABILITIES` followed by
`FED_CAPABILITIES_ACK`. It occurs only after Core version 2 is selected and the
Core peer is authenticated. It advertises Federation extension/object versions,
profiles, critical capabilities, and bounds only; it never carries a Core
version list. Both messages bind the authenticated session transcript.

Discovery separates `OPERATOR_RECORD_QUERY`/`OPERATOR_RECORD_RESPONSE` from
`ENDPOINT_RECORD_QUERY`/`ENDPOINT_RECORD_RESPONSE`. Authority retrieval uses
`OWNERSHIP_AUTHORITY_QUERY`/`OWNERSHIP_AUTHORITY_RESPONSE` for bounded
ownership/delegation chains and
`AUTHORITY_PROOF_QUERY`/`AUTHORITY_PROOF_RESPONSE` for compact proofs. Delivery
never grants authority before the returned signed objects validate.

Trust synchronization distinguishes `TRUST_BUNDLE_REQUEST`,
`TRUST_BUNDLE_RESPONSE`, `TRUST_BUNDLE_UPDATE`, and `TRUST_BUNDLE_ACK`.
Acknowledgement binds the exact digest and processing result but is not
normative bundle acceptance. Transparency uses `CHECKPOINT_QUERY`,
`CHECKPOINT_RESPONSE`, `INCLUSION_PROOF_REQUEST`,
`INCLUSION_PROOF_RESPONSE`, `CONSISTENCY_PROOF_REQUEST`,
`CONSISTENCY_PROOF_RESPONSE`, and `WITNESS_STATEMENT`.

Bilateral admission uses `AUTHORIZATION_REQUEST` and
`AUTHORIZATION_RESPONSE`; destination acceptance never replaces independent
source validation. Revocation uses distinct `REVOCATION_PUSH`,
`REVOCATION_ACK`, `REVOCATION_QUERY`, and `REVOCATION_RESPONSE`. The ACK binds
the exact accepted/rejected revocation state, reason, enforcement, and digest.
Conflict evidence uses `CONFLICT_REPORT` and `CONFLICT_ACK`; neither delivery
nor acknowledgement creates conviction or unilateral revocation authority.

Lifecycle synchronization uses `OPERATOR_STATUS_QUERY`,
`OPERATOR_STATUS_RESPONSE`, `QUARANTINE_NOTICE`, `RECOVERY_NOTICE`, and
`REENTRY_EVIDENCE`. Notices create no authority by delivery. Explicit object
operations are `OPERATOR_REGISTRATION_REQUEST`,
`OPERATOR_REGISTRATION_RESPONSE`, `OPERATOR_RECORD_UPDATE`,
`OPERATOR_RECORD_UPDATE_ACK`, `KEY_AUTHORIZATION_PUBLISH`,
`KEY_AUTHORIZATION_ACK`, `KEY_AUTHORIZATION_UPDATE`,
`KEY_AUTHORIZATION_UPDATE_ACK`, `NAME_OWNERSHIP_PUBLISH`,
`NAME_OWNERSHIP_ACK`, `NAME_OWNERSHIP_UPDATE`,
`NAME_OWNERSHIP_UPDATE_ACK`, `DELEGATION_PUBLISH`, `DELEGATION_ACK`,
`DELEGATION_UPDATE`, `DELEGATION_UPDATE_ACK`, `ENDPOINT_RECORD_PUBLISH`,
`ENDPOINT_RECORD_ACK`, `ENDPOINT_RECORD_UPDATE`,
`ENDPOINT_RECORD_UPDATE_ACK`, `CONFLICT_RESOLUTION_PUBLISH`,
`CONFLICT_RESOLUTION_ACK`, `APPEAL_REQUEST`, and `APPEAL_RESPONSE`.

The machine registry supplies every message's exact value, sender/receiver
roles, class, replay context, mutation behavior, idempotency, allowed protocol
state, associated object, authority effect, and reason for existence. Those 58
semantic entries derive the count; no message is retained to meet a count.

## Detailed F114 lifecycle semantics

The exact top-level lifecycle allocation order is `APPLIED`,
`VERIFICATION_PENDING`, `VERIFIED`, `PROVISIONAL`, `ACTIVE`, `SUSPENDED`,
`QUARANTINED`, `RECOVERY`, `RETIRED`, `TERMINALLY_REVOKED`, and `REJECTED`.
`RESTRICTED` is a decision/outage outcome, not lifecycle. `REJECTED` grants no
authority. `PROVISIONAL` grants only explicit time/scope/resource-bounded pilot
authority. Unknown, skipped, rollback, or invalid transitions fail
`REJECT/ERR_CONTINUITY` without mutation; terminal tombstones never resurrect.
Numeric lifecycle values are identifiers, not transition ranks. Monotonicity
applies to identity generation and record sequence under valid continuity.
The exact allowed transition graph is normative in the machine registry; it
includes gated `RECOVERY -> ACTIVE` and has no outgoing transition from
`RETIRED`, `TERMINALLY_REVOKED`, or `REJECTED`.

When and only when lifecycle is `RECOVERY`, `recovery_stage` is required and is
exactly one of `RECOVERY_PENDING`, `RECOVERY_VERIFIED`, or
`REENTRY_RESTRICTED`. It is forbidden otherwise. Normal `ACTIVE` follows
`REENTRY_RESTRICTED` only after peer synchronization, compatible checkpoints,
current revocations, monitoring, and readiness gates pass. `REQUESTED`,
`EVIDENCE_VERIFIED`, `APPROVED`, `ACTIVATED`, `REENTRY_MONITORING`, `COMPLETE`,
and local `REJECTED` are implementation workflow labels only, never wire
registry or signed-object values.
Stages advance only `RECOVERY_PENDING -> RECOVERY_VERIFIED ->
REENTRY_RESTRICTED -> ACTIVE`; skips and rollback fail without mutation.

## Detailed F116 appeal and recovery separation

Appeal reviews retained evidence under the independent appeal authority. It is
not a recovery approval, cannot replace recovery thresholds, cannot erase
conflict evidence, and cannot reactivate a retired or terminally revoked
identity. Continuity-preserving recovery retains the Operator ID at a higher
identity generation. Lineage-breaking recovery permanently tombstones the old
ID and requires a new genesis-derived ID.

## Detailed validation and failure behavior

Resource/parsing, canonical encoding, cryptography, identity/purpose, schema,
authority/scope, monotonic continuity, revocation/terminal state,
transparency, freshness/outage, and local policy validate in that order before
mutation. Queries and notices do not mutate authority. Responses, updates,
pushes, publications, evidence, and ACKs mutate only the explicitly named
candidate/cache/audit/result state in the machine table. Same replay context
and canonical digest is idempotent; altered digest or context is replay or
equivocation as applicable. Unknown messages, lifecycle values, recovery
stages, critical capabilities, and reserved allocations fail closed without
state mutation.
