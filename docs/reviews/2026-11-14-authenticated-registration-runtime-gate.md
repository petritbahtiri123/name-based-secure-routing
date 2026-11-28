# Authenticated registration: runtime decision gate, 2026-11-14

Status: recommendation only, no runtime or wire-contract authorization.

## Actual boundary after the new evidence work

| Available | Still not established for connector runtime |
| --- | --- |
| Native exact signature primitive; signed purpose14 KAR fixture; bounded signed NOR/direct-delegation verification | Provenance/currentness of the supplied signer roots and the complete governing dependency closure |
| Native normal-revocation verification and connected negative owner effects under supplied test trust | Positive admission with all applicable controller, normal3/5 and emergency2/5 paths authenticated and enforced |
| Offline registration verifier binds request/peer/session/dependencies and test revision | Real resolver, authenticated freshness producer and serialized runtime commit |
| Offline configuration validates logical reference names | Opening and authenticating trust_ref/registration_policy_ref/registration_authority_ref |
| Local persistence/reopen and injected clock checks | Independently trusted nonregressing restart floors, crash/power-loss scope, approved real clock uncertainty |

The new native chain checker is a real verification prerequisite, not evidence
that those runtime columns are closed. Historical matrix paragraphs saying signed
positive KAR is absent are stale; the underlying governance obligations remain.

## Source evidence

- `crates/nbsr-transport/src/connector_registration.rs:34-44`: test-compiled
  synthetic Decision and Authority seam; future runtime must supply sealed
  verified authority. Lines321-329 and404-412 check/recheck decisions, but do not
  themselves establish the authenticity of their provider.
- `crates/nbsr-transport/src/connector_authority.rs:369`: registration_ready returns
  false; verify_normal_event begins at394. The preceding provider setup uses
  supplied reference inventories, not independently provisioned genesis trust.
- `deploy/single-instance/README.md` at HEAD: CONFIG_VALID_OFFLINE, ready:false,
  references_verified:false; no references opened, no provider/store selected.
- `docs/reviews/2026-10-11-registration-provider-contract-proposal.md` at HEAD:
  controller-only superseded; complete governing closure/currentness and trusted
  nonregressing restart required; signature success alone cannot issue a permit.
- `docs/reviews/2026-10-11-registration-full-model-acceptance.md` at HEAD:
  threshold policies, time/retention/cleanup/replay obligations remain separate.
- `nbsr/connector_registration_authority_offline.py::_evaluate`: existing exact
  policy/peer/delegatee/session/counter/record inventory binding provides the
  reference behavior; it explicitly assumes fixture trust, revision and freshness.

Some docs/config files are sparse-checkout omissions and were inspected with
`git show HEAD:path`; they were not restored or edited.

## Reconciliation with the approved Go client ACP boundary

This reconciliation inspected tracked sources at
`d6376d8279763dd57daaad21ea8ca43de8a90367`, including sparse paths through
`git show`. It is source inspection, not a new execution of historical acceptance
checks. Client mechanisms and connector governance are distinct scopes.

### Already decided and reusable, not open architecture choices

- `docs/architecture/production-go-client/tranche2-identity-authority-control-plane.md`
  records the approved enrolled Source Operator ACP boundary, bounded freshness
  polling rather than per-stream checks, and durable signed ACP generation floors
  plus mandatory fresh enrolled-ACP validation after restart. No live authority
  is restored. TPM is optional defense-in-depth, not a universal requirement.
- `docs/protocol/tranche2b-acp-wire-semantics.md` freezes only RouteGrant Acquire,
  Renew and Freshness. It does not define connector registration. Authenticated
  outer results do not replace independent verification of inner artifacts.
- `client/nbsr-go-client/internal/authority/http_provider.go` implements the bounded
  enrolled-operator HTTP/2/TLS1.3 transport; `runtime.go` resets readiness and obtains
  fresh identity-bound validation before ready; `restart.go` loads the floor,
  rejects regressions, and calls StoreHigher before publishing freshness.
- `client/nbsr-go-client/internal/authority/source_operator_runtime.go` exposes
  explicit bootstrap, enrollment, authority, signer and transactional-idempotency
  seams. These are reusable mechanisms, not a connector authority backend.

### What completion evidence does and does not establish

`docs/protocol/tranche2b-implementation-status.md` records 3R-C completion within
its transport/enrollment/runtime scope, including real HTTP/2 lifecycle evidence.
Its durable enrollment-identity and idempotency storage evidence must not be
relabelled as durable ACP generation-floor storage or production freshness proof.

In `client/nbsr-go-client/internal/authority/types.go`, GenerationFloorStore.Load
requires distinguishing authenticated pristine absence from deletion, rollback or
uncertain loss after a floor existed. Its comment explicitly reserves durable
adapters for later. A whole-repository tracked Go search for StoreHigher found
only the non-test implementation in `internal/authority/floor.go`:
MemoryGenerationFloorStore, expressly fixture/test storage without production
durability. Searches for generation/durable-floor references in tracked Go, Rust
and Python found no separate implementation of that ACP floor. This is a scoped
source-search finding, not proof that no differently named persistence exists.

`internal/authority/runtime_test.go` uses that memory store with
runtimeCheckpointVerifier, which supplies fixture freshness claims. Real transport
and lifecycle orchestration therefore do not demonstrate a production signed
freshness verifier or durable floor surviving a real process/storage restart.

The separate `docs/reviews/2026-10-11-inclusion-persistence-design.md` does describe
local watermark/primary persistence and recovery. It requires an independently
supplied expected digest, does not fsync the parent directory, and does not turn
restoring two old valid files into independently detected rollback. It is not the
missing ACP generation-floor backend or a complete connector freshness source.

## Next substantive connector runtime gate

Do not reopen the approved client choices above. Define only their justified
applicability and the remaining connector-specific binding before implementing a
positive provider. Reuse existing reference names, signed objects, Option C and
approved governance mappings; do not allocate a replacement format by assumption.

The narrow unresolved questions are:

1. Which existing authenticated artifact and provisioned trust context supplies
   the complete connector governing dependency inventory, current revision and
   nonregressing denial/lineage floors? Bind the exact connector/service/operator/
   peer key/profile and preserve controller, normal3/5 and emergency2/5 semantics.
2. How does fresh startup/restart validation authenticate that connector inventory,
   including retained revocations and missing/corrupt/rollback-suspect state? The
   approved client freshness model is a reuse candidate, not an approved mapping
   from route-generation freshness to connector roster/revocation currentness.
3. Which approved clock/uncertainty and serialization boundaries bind verified
   changes to the final registration commit, event ownership and cleanup?

The frozen ACP operations do not establish this artifact mapping. Do not cast
DeviceIdentity or purpose15 ACP result authentication into connector governance,
turn client ready into connector READY, or substitute a single enrolled operator
for threshold authorization. Controller-only remains superseded, not a fallback.

Recommendation: review the exact artifact/currentness/floor binding first, reusing
approved client transport and startup patterns where the identities and scopes
actually match. If the existing wire contracts cannot carry the required evidence,
a scoped contract decision is needed before implementation. A separate durable
client floor adapter could be useful work, but would not itself close this
connector gate. Remain offline/fail-closed until the connector mapping and its
runtime composition are verified. No runtime or wire change is authorized here.

## Optional mechanical work while that decision is pending

A native exact REQUEST-to-KAR/ownership/delegation join can be useful if it closes
specific documented mix-and-match cases and is intended for reuse by the eventual
provider. It must bind the configured policy, actual peer key, service/operator/
gateway, delegatee, scope, complete canonical dependency inventory/digests and
session/request counter; reuse the Python offline checks above. It must NOT
implement Authority, construct Decision, claim freshness or change READY.

Do not call that additional test-only join a runtime milestone or build another
wrapper solely to show progress. The trust/currentness/restart decision is the
critical path, and was independently reviewed as such. No new code, keys,
dependencies, VM work, registry flags or publication are authorized by this note.

## Proposed trust and currentness decision — 2026-11-25

Status: direction approved by the user on 2026-11-25, limited to separating
provisioning, evidence distribution and Gateway verification, and preparing the
artifact mapping. No provider, wire amendment or runtime activation is approved.
The historical findings and full security model remain in force. The isolated
Docker lifecycle evidence does not close any trust/currentness gate below.

### Recommended source and division of responsibility

Use one explicitly configured registration-authority distribution service for the
connector's operator/profile, with independently authenticated governing evidence
verified at the destination Gateway. The service transports evidence; its TLS
identity or successful response alone cannot grant registration. One distribution
service does not mean one governance signer or controller-only authorization.
No concrete endpoint, operator key, accepted bootstrap or live service has been
selected or verified by this proposal.

| Existing reference | Proposed responsibility | Must not imply |
| --- | --- | --- |
| `trust_ref` | Independently provisioned, integrity-protected bootstrap: exact authority/profile identity, accepted roots and signer-purpose/governance policy versions, with authenticated provenance | Trust-on-first-use, roots learned solely from the endpoint being checked, or fixture signer inventories becoming real trust |
| `registration_policy_ref` | Exact connector/service/operator/Gateway/peer binding, allowed scope, governing dependency rules and applicable time/enforcement policy | Relaxed thresholds, broader delegation or a locally invented authority policy |
| `registration_authority_ref` | Explicit distribution endpoint identity and evidence-resolution policy bound to those same trust and scope references | Reusing a client RouteGrant endpoint/result as connector authority without an approved mapping |

These are responsibility assignments for existing logical references, not new
config fields or permission to open references now. Provisioning must authenticate
the bootstrap independently of the distribution response and retain its provenance.
Operational root/roster updates must follow their existing authorized lineage and
policy; a newer file or endpoint response is not authority to replace them.

Reuse the approved client transport/startup patterns where applicable: explicit
endpoint authentication, bounded requests, independently verified inner artifacts
and fresh validation after restart. Do not import Source Operator client enrollment,
DeviceIdentity or purpose15 result authentication as connector governance. The
transport mapping and any connector operations need their own reviewed contract.

### What a freshness result must establish

The resolver must assemble one authenticated, internally consistent view of the
complete governing dependency closure. It must verify identity/ownership/delegation,
current signer authorization, all applicable controller/normal3/5/emergency2/5
obligations, and applicable inclusion/witness evidence under the accepted policies.
A freshness publisher does not gain those governance powers by publishing a view.

Recommend independently signed, connector-scoped currentness evidence that binds:

- the configured authority/profile and exact connector/service/operator/Gateway
  scope, plus the canonical governing inventory or its authenticated digest;
- the relevant policy/roster/lineage identities, current revisions and retained
  denial/revocation state, including the authenticated coverage boundary proving
  that relevant updates were not omitted;
- an authenticated validity bound and the replay/order domain for that view.

These are semantic requirements, not allocated fields, a new signing purpose or
a claim that an existing checkpoint already carries them. Absence of a revocation
from an arbitrary fetched list proves nothing. Inclusion alone does not prove
complete coverage or currentness. Do not combine separately valid records from
inconsistent revisions into an admission view.

The first implementation prerequisite is an exact artifact mapping: for each
requirement, name the existing signed object, canonical binding, authorized signer
purpose/policy and verifier, or identify the specific missing contract. Preserve
existing Option C bytes and approved governance mappings. No existing connector
currentness object/publisher is established here; if the frozen objects cannot
express the required binding/coverage, propose a separately reviewed amendment.
Do not repurpose a route-generation checkpoint, purpose15 or global-trust-v1.

Propose bounded polling before verified freshness expires, with authenticated push
hints only to accelerate refresh. A hint, successful poll, retry or reconnect cannot
extend a signed validity bound or clear a retained denial. Unauthenticated input
cannot name an owner into revocation. Actual intervals and maximum offline trust
must be explicit approved profile limits, bounded by the earliest applicable
credential, governing evidence, policy and freshness expiry; no numeric default is
chosen here. Loss of freshness blocks new admission/renewal requiring that proof;
existing work follows its separate authority/drain policy, not invented termination.
Authenticated applicable termination still takes precedence over grace.

### Startup, restart and the final admission boundary

1. Authenticate the provisioned references and load scoped durable floors before
   accepting authority. Separate authority revision, lineage/denial state and
   request/session counters; never compare unrelated namespaces as one generation.
2. Distinguish authenticated first provisioning from missing, corrupt or uncertain
   previously established state. A local file pair, signature or MAC alone cannot
   detect restoration of an older valid snapshot. Require an independently trusted
   recovery anchor/currentness source and a reviewed durable storage contract.
3. Obtain fresh authenticated connector-currentness validation after every restart.
   Never restore live registration from disk. Reject regression, conflicting state
   at the same revision, incomplete coverage and replayed stale startup evidence.
   A newer number alone cannot clear an existing denial or authorize recovery.
4. Persist required higher floors before publishing the verified view. A write,
   ownership-release or crash outcome that is uncertain keeps admission blocked;
   recovery must reconcile it without lowering floors or silently reenrolling.
5. Use the approved bounded clock/uncertainty policy: expiry against latest
   plausible UTC, future enforcement only at earliest plausible UTC, with monotonic
   progress and invalid-clock latching. Neither local wall time alone nor transport
   reachability supplies authenticated freshness. The actual clock source and
   durable anti-rollback mechanism remain implementation decisions to review.
6. Only the verifier may issue an opaque authority result. At final serialized
   admission, recheck the current view, exact peer/service/operator/Gateway,
   connection/session/request counter and digest, dependencies and deadlines.
   A revision change between verification and commit invalidates stale acceptance.
   Apply authenticated events/timers through the same ownership boundary; failed
   cleanup retains quota and ownership until exact successful confirmation.

### Alternatives and scope of direction approval

| Approach | Assessment |
| --- | --- |
| Configured distribution service plus independent Gateway verification | Recommended: reuses transport patterns while retaining every applicable governance obligation and one serialized admission owner |
| Directly query each governing authority from the connector | Not selected: adds endpoint discovery, partial-view reconciliation and failure handling without removing completeness/currentness requirements |
| Reuse client ACP success, fixture authority or a Python IPC wrapper as a registration permit | Rejected: no established connector governance/currentness binding; a new IPC trust boundary would not solve it |

The user approved the recommended separation of provisioning, evidence
distribution and Gateway verification, and preparation of the artifact mapping.
That approval does not select an endpoint, signer-purpose allocation, storage backend,
clock policy, new wire message, production source overlay or live activation.

Before a positive provider implementation, the mapping must resolve: the actual
bootstrap provenance and authority identity; complete-currentness evidence and
publisher authorization; the independent restart anchor/durable-floor contract;
and clock/serialization limits. Each must identify an existing approved contract
or a specific amendment for review. No controller-only operational fallback.

### Acceptance evidence still required for Stage 3

After those decisions and separate implementation/runtime authorization, require:
real authenticated register/renew without reconnect; rejection of wrong-purpose,
wrong-scope, stale, incomplete and mixed-revision evidence; final-commit races;
all applicable authenticated enforcement paths and expiry/freshness-loss behavior;
restart with missing/corrupt/rolled-back state and interrupted floor writes; and
single ownership with failure/retry cleanup confirmed before replacement.
A future readiness consumer must derive eligibility from that current verified
registration, never TLS, offline config or fixture success. This draft creates no
READY path or Stage 3 closure. Final real-pilot security review remains a separate
gate; Docker lifecycle results are retained as supporting evidence only.

## Existing-artifact mapping — 2026-11-25

Status: mapping prepared for review under the approved direction above. Source
inspection at `82857ebb5f3b05c502eba05e34191c9ec3c948df`; no new runtime execution,
keys, signatures, reference resolution or activation. Historical test results are
not new passes. "Missing" below means not supplied by the cited artifact/path,
not a claim that every repository file or external service was audited.

### Trust, identity and registration inputs

| ID / requirement | Existing artifact and verifier | Exact reusable binding / signer role | Remaining gap |
| --- | --- | --- | --- |
| T1: provisioned trust and policy | [Offline config](../../deploy/single-instance/validate_config.py): `trust_ref`, `registration_policy_ref`, `registration_authority_ref`; [FederationTrustBundle](../../nbsr/federation/trust.py) | Config checks logical reference syntax only. Bundle semantics retain identity-root references, thresholds, validity and lineage; they must themselves be authenticated under the applicable trust-update policy | No authenticated opening of these references, selected real bootstrap/endpoint or independently established initial bundle provenance. A valid self-contained bundle cannot bootstrap trust in its own signer |
| T2: exact transport-key authorization | `KeyAuthorizationRecord` via [verify_federation_sign1](../../nbsr/federation/cose.py); native test-only [connector_kar.rs](../../crates/nbsr-transport/src/connector_kar.rs) | KAR is signed by `IDENTITY_ROOT` purpose 1; its authorized child key is `FEDERATION_TRANSPORT` purpose 14. Verify operator, key ID/public key, authorizer, lifecycle and validity; the two purposes are not interchangeable | Native gate is genesis-only under `SuppliedTestRoot`; real root provenance, current revocation/lineage and runtime composition are not supplied |
| T3: ownership and delegation | `NameOwnershipRecord`, `DelegationRecord`; [DelegationVerifier.verify](../../nbsr/federation/delegation.py); native [connector_genesis.rs](../../crates/nbsr-transport/tests/support/connector_genesis.rs) | NOR signer purpose 5, delegation signer purpose 6; signed ancestry, parent digest, delegatee and allowed scope. Native bounded chain reuses exact signed bytes | Supplied native signer contexts and three-object genesis fixtures do not establish the complete governing closure, rotation/recovery or independently current signer membership |
| T4: join registration to verified evidence | [OfflineRegistrationAuthority](../../nbsr/connector_registration_authority_offline.py), `_evaluate` / `validate`; [development REQUEST vector](../../vectors/connector-registration-development-v1/request.cbor) | Policy fields 2,3,4,5,6,7,8,12; SHA256 of actual peer key equals field 8; KAR digest field 9; canonical sorted typed dependency refs field 10 and their digest field 11. Also exact connection/session/request-counter correlation and raw-request digest | Exact inventory, signer inventory, positive revision, `freshness_ref` and expiry are constructor-supplied fixtures. Offline receipt identity is not a runtime/IPC trust boundary; fixture action 24576 is not a new production allocation |

The current native request/evidence join is narrower than T4: it returns a checked
request digest and inclusive evidence-expiry bound, not the freshness-limited
exclusive admission ceiling, session/counter verification or a permit. See the
[existing binding review](2026-11-14-native-request-evidence-binding.md). Reuse
those checks without treating their supplied inventory as authenticated provisioning.

The [Option C registry](../protocol/registries/federation-v0.1-threshold-container-proposal.json)
and its [literal-vector verifier](../../scripts/verify_federation_threshold_container_fixtures.py)
are the existing threshold-format references. They are not deployment approval.
The Python single-Sign1 verifier explicitly rejects FederationTrustBundle
packaging; T1 therefore cannot be implemented by passing a bundle to that verifier
and assuming it authenticates the governing quorum. Exact applicable named-policy,
signer-purpose and accepted-version selection must be retained in M1/M2.

### Governing changes and freshness

| ID / requirement | Existing artifact and verifier | What it establishes | Remaining gap / prohibited substitution |
| --- | --- | --- | --- |
| G1: applicable revocation governance | `TypedRevocationRecord` / `SemanticThresholdEvidence` in [revocation.py](../../nbsr/federation/revocation.py); existing Option C and [normal conformance amendment](../protocol/registries/federation-v0.1-normal-revocation-conformance-v1.json), checked by [normal_revocation_conformance.py](../../scripts/normal_revocation_conformance.py) | Explicit local normal 3/5 mapping (`normal-revocation-v1`, `normal-revocation`), typed enforcement, eligible signer and context checks; normal fixture revocation keys use purpose 12. Controller and emergency 2/5 obligations remain separately applicable | Local amendment is not runtime authorization or authentic roster provenance. `SemanticThresholdEvidence.from_transport` does not provide the live decoder. Do not substitute global-trust-v1, a bare Sign1 list, controller-only operation or the freshness publisher for required governance |
| G2: signed record inclusion and continuity | `TransparencyCheckpoint`, `InclusionProof`, `ConsistencyProof`, `WitnessStatement`; [TransparencyVerifier](../../nbsr/federation/transparency.py), [COSE witness authentication](../../nbsr/federation/cose.py); [local v2 inclusion amendment](../protocol/registries/revocation-inclusion-local-v2.json) and [verify_package](../../scripts/revocation_inclusion_v2.py) | Exact signed v2 record bytes, prior anchor and detached inclusion evidence, checkpoint continuity and applicable witness confirmation. Log purpose 8 and witness purpose 9 are distinct. Retained event bindings/denials prevent repeated application in the local state oracle | Inclusion of one record and append-only consistency do not prove complete relevant revocation coverage or freshness of the connector's entire dependency inventory. Governing log/witness provenance and independent restart anchors remain external; historical v1 is not silently reinterpreted |
| G3: verified negative effect on an owner | Test-only [LocalAuthorityProvider](../../crates/nbsr-transport/src/connector_authority.rs), `verify_normal_event` / `apply_verified_event` | Native normal-event verification, exact target/dependency binding, bounded time and confirmed-cleanup retention under supplied test trust; `registration_ready()` remains false | This is a negative enforcement bridge, not an all-mode positive registration provider. Supplied governing roots/rosters are not real bootstrap; normal-path success does not implement every controller/emergency path |
| F1: existing client freshness transport | [Frozen ACP wire semantics](../protocol/tranche2b-acp-wire-semantics.md); [HTTP provider](../../client/nbsr-go-client/internal/authority/http_provider.go), [ProviderFreshness / verifier interface](../../client/nbsr-go-client/internal/authority/types.go) | Client Acquire/Renew/Freshness transport and authenticated outer results; purpose 15 signs the outer ACP result only. Inner evidence is independently checked through `VerifyFreshnessEvidence`; client scope is SourceOperator/profile and its authority-generation context | No approved mapping to connector inventory completeness, governing roster/revocation coverage or connector restart validation. The interface and opaque evidence bytes do not define the missing signed connector artifact; transport success is not freshness |
| F2: complete connector-currentness evidence | No matching complete producer/consumer contract established by T1–F1. Offline authority takes injected `freshness_ref`, `freshness_expires`, `revision`; native negative provider uses supplied trust | Existing checks show where freshness and revision must bind; they do not authenticate the source of those values | Missing exact canonical object/version, authorized signer purpose/policy and provisioning, identity/inventory binding, coverage/completeness semantics, conflict/order domain, validity and startup anti-replay proof. No new field, purpose, endpoint or TTL is allocated by this mapping |

F2 is the critical artifact gap. The next decision must name the signed bytes and
verifier inputs proving both a current view and the completeness of all governing
updates for that scope. A log timestamp, higher counter, absence from a returned
list, transport-level nonce or fresh TLS connection alone is insufficient. A
request-correlated response can help prevent replay only if its approved signature
binding and governing coverage/currentness semantics actually establish that proof.

### Restart, time and serialized ownership

| ID / requirement | Existing artifact and verifier/coordinator | Reusable behavior | Remaining gap |
| --- | --- | --- | --- |
| R1: nonregressing startup gate | `SignedGenerationFloor`, `GenerationFloorStore` in [types.go](../../client/nbsr-go-client/internal/authority/types.go); [RestartGate.Load / AcceptFresh](../../client/nbsr-go-client/internal/authority/restart.go); [MemoryGenerationFloorStore](../../client/nbsr-go-client/internal/authority/floor.go) | Floor binds SourceOperator/profile, generation, checkpoint digest and signed evidence. Store higher verified state before publishing freshness; distinguish authenticated pristine absence from loss/rollback; require fresh startup validation | The named Go store is explicitly memory/test storage. The struct itself is not a signed object or proof of durable storage. Connector scope, independent trusted floor/recovery anchor, durable adapter and real signed freshness verifier are not established by this path |
| R2: local inclusion-state persistence | [Snapshot / Repository](../../scripts/inclusion_persistence.py), `load(expected)` / `apply`; [historical filesystem-trial record](2026-10-11-inclusion-filesystem-matching-module.md) and [persistence design](2026-10-11-inclusion-persistence-design.md) | Preserve exact record/event/denial state, context binding, transaction lineage and watermark-first replacement. Load requires an independently supplied expected digest; uncertain commit retains a latch | Storage-neutral coordinator and separately scoped filesystem trial are not the ACP floor backend or complete connector restart store. Restoring both old valid files is not detected without an independent anchor; process-crash/power-loss and recovery provenance remain separate gates |
| R3: clock and deadline enforcement | [OfflineAuthorityTimer](../../nbsr/connector_authority_timer_offline.py); native `TimeWindow`, `observe`, `fresh` in [connector_authority.rs](../../crates/nbsr-transport/src/connector_authority.rs) | Explicit polling, latest/earliest plausible bounds, monotonic observation and invalid-time behavior; preserve distinct authority/admission/work deadlines | Time inputs are supplied fixtures. Real clock source, uncertainty policy, suspend/resume behavior and scheduling guarantees need an approved contract and execution evidence; no polling interval or outage grace is invented here |
| R4: final owner commit and cleanup | Test-only [Gateway](../../crates/nbsr-transport/src/connector_registration.rs) and [CleanupTicket](../../crates/nbsr-transport/src/connector_cleanup.rs); [isolated Docker fixture](../../interop/nbsr-go-peer/connector/README.md) | Existing decision checks/rechecks, exact cleanup attempts, retained quota/ownership, explicit retry and no replacement before confirmation | `Authority`/`Decision` are synthetic test seams. Bind a sealed real verifier result, current revision and authenticated event dispatch to this serialized owner before positive admission; Docker supervisor receipts are not authority artifacts |

The exact `scripts/inclusion_filesystem_trial.py` path named by older guidance is
not tracked at this inspected commit. R2 links the retained historical trial
record, not a currently executable adapter; this mapping does not restore or
claim to rerun that old local harness.

Keep R1's authority-generation floor, R2's record/checkpoint history and R4's
session/operation counter domains distinct. Persistence of one is not persistence
of the others. No restore path may reconstruct live registration or clear retained
denials merely because a file is valid, a number increased or the endpoint replied.

### Missing decisions and the smallest next deliverable

| Gap | Required decision artifact before positive provider work | Existing material to reuse |
| --- | --- | --- |
| M1: real bootstrap/provisioning | Identify the operator/profile, accepted root/policy version and exact independently authenticated provisioning/rotation procedure for T1; keep real secret material out of this document | Existing reference names, KAR/ownership/delegation and bundle policies; no trust-on-first-use |
| M2: signed complete-currentness mapping | Produce the F2 field-by-field semantic mapping to existing canonical signed objects, with exact signer authorization, governing coverage and anti-replay/conflict semantics. If no existing object can carry them, submit one narrowly scoped versioned amendment for review | Existing canonical codecs, Option C and approved normal/inclusion amendments; existing client transport patterns only where identity/scope match |
| M3: restart provenance and durability | Specify the connector floor namespace, independent recovery anchor, authenticated first-provisioning distinction, write/publish ordering and recovery from missing/corrupt/rolled-back/interrupted state | R1 gate pattern and R2 persistence invariants, without claiming their current test backends solve the deployment problem |
| M4: time and runtime composition | Specify the real uncertainty source/limits, authenticated event delivery and final serialized verifier-to-owner handoff; maintain all applicable governance paths | R3 deadline rules and R4 ownership/cleanup invariants |

Prepare M1/M2 as the next reviewable contract decision, with M3/M4 dependencies
explicit. Until each artifact has an approved source, scope and verifier mapping,
positive provider implementation remains blocked; do not add another fixture
wrapper as a substitute. Review evidence must cover substituted roots/purposes,
incomplete and mixed-revision views, omitted valid revocations, same-revision
conflicts, stale startup responses, rollback of both retained files, interrupted
floor publication and revision changes before final commit. These are future
acceptance requirements, not tests executed by this documentation update.

No existing protocol registry, authority overlay, runtime/live flag or source
verifier changes in this mapping. It does not authorize new signatures, credentials,
a live endpoint, READY, deployment, commit or push. Stage 3 remains open.

## Proposed M1/M2 provisioning and currentness contract — 2026-11-25

Status: contract draft for review. The user approved the direction and preparation
of this contract, not these new semantics, publisher trust, wire encoding or runtime
implementation. Normative words below describe the proposed acceptance contract
only. No new format/purpose/action is allocated. Existing frozen objects and typed
governance rules remain unchanged; unresolved wire bindings are explicit blockers.

### Contract choice and security assumption

Recommend an explicit local bootstrap import plus a full-state currentness response
verified at the Gateway. Initially require a complete snapshot for the configured
scope, not deltas or a caller-selected subset. This is a proposed first supported
profile, not a change to existing object formats or an unbounded inventory limit.

Separate three roles: the provisioning authority approves the initial trust and
policy context; governing authorities sign the records and enforcement decisions;
an explicitly authorized currentness publisher attests the coverage/currentness
of the assembled view. The distribution endpoint may relay their signed bytes but
cannot create any of those roles merely by serving them. Publisher and endpoint
may be operated together only if each authorization is independently established.

Completeness is a trust-bearing assertion: membership proofs and valid individual
signatures cannot prove that a publisher withheld no applicable update. Approval
must identify the publisher's authoritative update sources and its obligation to
observe every governing domain in scope. Trust in this obligation is additional
to trust in record signers. Compromise of that publisher can hide newly issued
revocations until another trusted observation exposes the omission; signatures
alone do not eliminate that risk. A profile unwilling to accept that assumption
must define independently authenticated coverage attestations for every domain
before implementation. Do not imply that ordinary log witnesses already attest
this coverage or silently substitute a single operator for governance quorums.

### M1: authenticated bootstrap import

Recommended bootstrap path: an explicitly authorized local provisioning operation
imports one bounded package whose identity/digest is checked against an expected
value obtained through an independently authenticated commissioning channel. The
same untrusted download cannot supply both package and trusted expected value.
The actual commissioning authority, channel and verification procedure must be
selected before this path can be implemented or used; none is provisioned here.

The accepted package MUST bind the following semantic inputs as one context:

| Input | Required binding |
| --- | --- |
| Identity and scope | Provisioning instance/epoch, authority and profile, operator, connector identity/actual peer key, service and canonical Gateway identity; preserve existing ID types and scope semantics |
| Governing trust | Exact accepted root/roster/policy versions and authenticated provenance, including authorization for all applicable controller, normal3/5 and emergency2/5 paths |
| Publisher trust | Exact publisher identity/key authorization, permitted coverage domains and validity; this role attests currentness only, never record issuance, revocation override or root replacement |
| Distribution | Explicit endpoint and expected TLS identity, permitted operation/profile and independently verified inner-evidence policy; no discovery or trust-on-first-use fallback |
| State and time policy | Distinct authority/lineage/denial namespaces, authenticated initial/recovery anchors and required clock/freshness/resource limits; unknown required values prevent acceptance |
| Reference join | Exact content identities/digests for the three existing logical references, bound to the same provisioning context rather than independently swappable paths |

The reference join is resolver metadata, not permission to add config keys or
change the offline validator. Provisioning authenticates reference contents; it
does not grant registration. Secrets/private keys are not package evidence and
must never enter reports, patches or ordinary logs.

Import procedure: authenticate the commissioning decision and expected package;
parse bounded canonical evidence with the existing relevant validators; verify
identity/purpose/lineage and all cross-reference bindings; establish authenticated
first provisioning or validate a separately authorized successor; durably record
the accepted context and initial anchors together before exposing it to a resolver.
Any partial/uncertain write remains unavailable for new authority-dependent use.
A local operator's import permission is not authority to rewrite governing policy.

A missing prior context is not proof of first installation. Deletion, corruption
or rollback suspicion MUST enter explicit recovery with independently authenticated
state; never recreate a pristine context automatically. Successor packages MUST
follow existing governing replacement/rotation rules, retain required denial and
lineage floors, and invalidate in-flight checks tied to the replaced context.
Changing an endpoint cannot change roots or publisher authorization implicitly.
Reprovisioning must not become a route around revocation or failed cleanup.

### M2: signed full-state currentness response

The Gateway/verifier issues a fresh, bounded request correlation challenge for
one scope and provisioning context. The publisher response MUST authenticate that
challenge and the exact snapshot commitment. This is separate from registration
session IDs/operation counters. Challenge generation, encoding, domain separation
and limits require the wire contract below; no existing field is repurposed here.

The following labels are semantic slots, not allocated wire field names/numbers:

| Slot | Required signed meaning and verification |
| --- | --- |
| Context | Exact protocol/version, authority/profile, provisioning-context digest and configured subject/scope. Reject cross-profile, cross-operator, cross-Gateway or peer substitution |
| Correlation | This outstanding verifier request, its fresh challenge and context. A TLS session or unrelated client ACP RequestID cannot supply this binding |
| Inventory | Canonical complete typed dependency inventory, its digest, and exact immutable signed record bytes or authenticated references resolving to those bytes; every reference must resolve before acceptance |
| Governing coverage | Enumerated governing domains and accepted source identities; per-domain revision/checkpoint/watermark and authenticated completeness assertion for all applicable records, replacements and enforcement updates through that cut |
| Consistent view | A manifest committing all inventory and coverage components together, including roster/policy/lineage versions. Cross-domain cuts must satisfy explicit consistency/dependency rules; unrelated counters cannot be collapsed into one scalar order |
| Denial continuity | Applicable retained revocations/denials, future-effective events and authorized lineage transitions. Omission is never permission to erase a retained denial or cancel a scheduled authenticated event |
| Time | Authenticated observation/coverage time and absolute validity bound, constrained by the approved clock, publisher authorization and governing evidence limits; re-signing or retransmitting old coverage cannot reset its age |
| Publisher authorization | Exact authorized key identity, role, scope, policy/version and current validity, with a verification path to the accepted provisioning context; no purpose15 or self-authorizing signer substitution |

The complete governance view is distinct from the REQUEST field 10/11 dependency
inventory. Its exact join to that inventory must be specified without silently
adding request fields, changing existing digest rules or rewriting frozen vectors.

A complete view covers every governing dependency, including authorization of its
signers and the publisher itself. Resolve these through an accepted anchored
validation policy; the publisher cannot attest its own unrevoked status solely
through the response it signs. An unverifiable/circular authorization path fails
closed. Existing independent trust anchors terminate validation, not an invented
infinite chain or a fixture registry.

Coverage means all relevant updates accepted by each identified authoritative
source through its authenticated cut. It does not mean all updates issued anywhere
at the instant of admission. Approval must specify the bound on source ingestion
lag, maximum accepted coverage age and maximum offline use; otherwise the profile
cannot claim currentness or accept new registration. Inclusion/consistency proofs
and applicable witnesses support their existing claims only. A Merkle root with no
approved completeness semantics cannot satisfy the coverage slot.

Each governing signature, purpose, scope and threshold MUST still be independently
verified. The publisher cannot make invalid records valid, lower quorum, authorize
an unsupported mode, drop known denials or extend governing expiry. If any required
domain is unavailable, incomplete, stale, inconsistent or over its declared bounds,
there is no partial-view acceptance or controller-only fallback. Snapshot size,
dependency depth, pending attempts and retry work MUST have explicit bounded limits;
exhaustion cannot evict retained safety state to manufacture success.

### Verification, publication and failure behavior

1. Capture the accepted provisioning context, current scoped floors and one live
   request attempt. Resolve only the configured endpoint/evidence paths; enforce
   bounded parsing and authenticate outer correlation before considering a candidate.
   Outer authentication never replaces verification of inner signed evidence.
2. Authenticate publisher authorization from the anchored context. Verify the
   snapshot commitment, every required dependency and governing mode, complete
   coverage, cross-domain consistency, denial continuity and bounded time. A claimed
   higher revision with missing or invalid components is not a usable successor.
3. Compare the candidate to retained state in its exact namespaces. A lower floor
   is rejected. At the same revision/cut, the canonical state commitment must agree;
   a differently signed challenge wrapper may wrap the same state without creating
   new authority. Conflicting authenticated state blocks new use pending explicit
   reconciliation, without rewriting floors or fabricating terminal revocation.
4. Under serialized ownership, recheck context/revision/time, exact outstanding
   challenge and cancellation state. Persist required higher safety floors and
   retained events before publishing the view. Discard stale completions. Consume
   the request once for publication; duplicate responses cannot repeat mutation,
   extend freshness or create another owner. Uncertain persistence latches new-use
   admission off until reconciled; it never releases owned quota.
5. Return an opaque verified-view result, not a registration permit. The eventual
   registration provider still joins exact peer/service/operator/Gateway,
   connection/session/request counter and digest, then rechecks current authority
   at final commit. This draft does not implement that provider or a READY consumer.

On every process restart the view starts unavailable and pending challenges are
not restored. R1/R2 anchors must be authenticated and fresh M2 validation obtained;
a disk snapshot or a replayed response from a previous boot cannot restore live
authority. This contract depends on M3 durability/independent recovery and M4 clock/
serialization decisions; a successful in-memory test cannot discharge them.

Reject invalid/unrelated bytes without changing an existing owner's authority,
denials or current verified view. Independent expiry/loss of valid freshness closes
new admission and proof-dependent renewal; authenticated applicable termination
still applies to existing work. Otherwise existing work follows its separately
bounded authority/drain policy. Network failure, refresh retries and hints cannot
restart grace, clear a latch or confirm cleanup. A previously verified view may be
used only within all existing signed bounds and the approved offline-use limit;
startup has no cached-view fallback. Exact failed-cleanup ownership is retained.

### Wire and deployment decisions still required

The recommended full-state/challenge contract requires a narrow versioned binding
if existing signed objects cannot express it. Before implementation, submit the
exact canonical payload and signed transcript, approved signer role/purpose and
policy authorization, object/version/action/ALPN placement, coverage semantics and
limits, correlation/replay rules and independently checked vectors. Reuse existing
records and Option C unchanged; do not modify frozen registries to fit this draft.
No purpose number, new endpoint URL, key, threshold policy or TTL is selected here.

The deployment review must additionally identify the actual commissioning authority
and independent channel, accepted bootstrap provenance, publisher's authoritative
feeds and completeness responsibility, its non-circular authorization/revocation
path, and M3/M4 implementations. These are explicit unfilled deployment inputs, not
implicit defaults. Approval of the architecture direction is not approval of this
new publisher trust assumption, this contract or any later runtime activation.

### Contract acceptance cases (required, not executed)

| Case | Required outcome |
| --- | --- |
| Correct independently authenticated import, then full valid currentness | Accept provisioning context and verified view only; no registration/READY side effect |
| Package and expected digest supplied only by the same untrusted endpoint | Reject bootstrap; no trust-on-first-use |
| Swapped reference, root, publisher purpose, operator/profile/peer or Gateway | Reject; preserve established context and floors |
| Valid individual signatures but a detected omitted retained revocation/required domain, incomplete manifest or mixed cuts | Reject view; known denials and scheduled events remain retained |
| Fresh challenge around old/stale coverage, or coverage with unknown ingestion bound | Reject; no freshness extension |
| Self-authorizing/revoked publisher, or incomplete publisher authorization path | Reject; endpoint TLS and publisher signature cannot repair the path |
| Lower state, conflicting state at one revision, or older provisioning epoch | Reject; conflict requires reconciliation; no floor reset |
| Replayed previous-boot response, duplicate completion, cancellation or context change during verification | No new publication/owner; retry needs a valid current request and context |
| Missing/corrupt state, rollback of both files or interrupted durable publication | No restored authority; retain uncertainty and require independently anchored recovery |
| Freshness expires or an authenticated termination becomes effective during admission/cleanup | Final serialized checks enforce the applicable rule; no stale acceptance or premature ownership release |

The omission case covers gaps detectable against trusted coverage requirements,
provided proofs and retained state. It does not claim cryptographic detection of
a coherent false completeness assertion hiding an update never observed through
any trusted source. That residual publisher-trust assumption requires explicit
approval or an independently authenticated coverage design.

Only after review of these semantics and the exact artifact bindings may a bounded
implementation be proposed. Real registration, Stage 3 closure and any pilot need
their separate authorization and measured acceptance; none follows from this draft.

## Concrete wire, publisher authorization and freshness proposal — 2026-11-25

Status: the user approved `nbsr-connector-currentness-draft1`, version 1, as a
draft for offline positive/negative vectors on 2026-11-25. This is not a frozen
production allocation or authorization of runtime trust, deployment or READY.
All field numbers below are local to these proposed CBOR maps, never additions to
Core/Federation/registration registries. Earlier sections describe constraints;
this section proposes their concrete realization. No registry or executable changes.

### W1: transport, encoding and cryptographic framing

Propose a separately configured HTTPS POST path `/nbsr/connector/currentness`,
TLS 1.3 with HTTP/2 ALPN `h2`, exact pinned endpoint identity and mutually
authenticated Gateway transport identity. That identity only permits this query;
it is not a Connector registration credential or governance authorization.
Do not reuse `/acp/authority`, its operations, a registration message code or
`nbsr-connector-dev-1` for this exchange. No redirects, endpoint discovery,
compression, content negotiation fallback, cookies or cached HTTP responses.
Use `application/cbor`, `Cache-Control: no-store`; only HTTP 200 with a valid
body can yield a candidate view. Empty-body 400/403/409/413/503 are query failures,
not authenticated revocations. Network policy and actual endpoint remain unselected.

Use existing deterministic CBOR rules: minimal integers, canonical map order,
no duplicate/unknown keys, indefinite lengths, floats, trailing bytes or implicit
coercion. Every listed map key is required; only explicitly nullable slots accept
null. Use existing tagged COSE_Sign1 (tag 18), protected headers exactly
`{1: -8, 4: kid}`, empty unprotected map, Ed25519 signature of 64 bytes and
`kid` length 1–64 bytes. `external_aad` stays empty as in the existing primitive.
Domain separation is in the mandatory signed payload literal, version and context;
reject a mathematically valid signature with the wrong domain or authorized role.
No new global key-purpose integer is claimed.

Notation: `b32` = exactly 32 bytes; `u64` = unsigned integer at most 2^64-1;
`time` = integer UTC seconds in 0..253402300799. Epochs/revisions start at one,
never wrap and have independent namespaces. Sorted Ref arrays use lexicographic
order of their deterministic CBOR bytes; b32 domain IDs use bytewise order. `D(x)` is SHA256 of exact deterministic
CBOR encoding of x, not JSON, a parsed object's arbitrary re-encoding or its COSE
wrapper. Raw retained signed objects keep their original bytes and existing hashes.

### W2: scope and request

`Scope` is the exact map `{0: operator_id, 1: service_id, 2: gateway_id,
3: connector_peer_key_sha256, 4: registration_profile}`. Fields 0/1/3 are b32;
field 2 is the existing canonical Gateway text64, with no normalization or hashing;
field 4 is the exact configured registration profile, UTF-8 text of 1–64 bytes.
The peer digest binds the actual Connector transport key, not the querying Gateway
TLS key. Existing identifier derivations remain unchanged. Context digest is
`D(["NBSR-Connector-Provisioning-Context-draft1", 1, package_bytes])`, where
package_bytes are the exact independently authenticated canonical provisioning
package bytes. The package contains no copy of its own digest; external references
are committed by their exact authenticated content identities.

| Request key | Type / exact meaning |
| --- | --- |
| 0 | Literal `NBSR-Connector-Currentness-Request-draft1` |
| 1 | Integer 1 |
| 2 | b32 accepted provisioning-context digest |
| 3 | Scope |
| 4 | Fresh unpredictable b32 verifier challenge from a CSPRNG; also the query-attempt identifier |
| 5 | b32 current retained safety-state commitment |

Define field 5 as `D(["NBSR-Connector-Retained-State-draft1", 1, context_digest,
canonical_floor_vector, sorted_retained_denial_refs, sorted_pending_event_refs])`.
These inputs come from authenticated durable local state, never caller assertions.
The floor vector is sorted by domain ID and contains `[domain_id:b32, epoch:u64,
revision:u64, state_commitment:b32]`. A newly provisioned vector comes only from
the accepted bootstrap; missing local files cannot synthesize an empty first boot.
The commissioning context assigns distinct domain IDs for governing-source floors
and publisher-status floors; duplicate namespace assignments are invalid. This
digest binds the attempt; it does not disclose the floor contents or let the
publisher redefine them. Local component-wise comparison is still mandatory.

Request bytes are canonical CBOR, carried on the authenticated transport; no new
application request-signing purpose is introduced. Their digest and challenge must
be authenticated in both returned signatures. The server binds the requested
context/scope to the allowed Gateway transport identity; arbitrary scope queries
are refused. The verifier keeps one outstanding attempt per scope/context and
never reuses a challenge, including across retry or restart.

### W3: snapshot and coverage structures

`State` is a map with these exact keys:

| State key | Type / meaning |
| --- | --- |
| 0 | Scope, byte-for-byte semantically equal to the request's canonical Scope |
| 1 | Artifact array, sorted by canonical Ref encoding, unique by Ref |
| 2 | Coverage array, sorted by unique domain ID; exact domain set required by the accepted policy |
| 3 | Sorted unique Refs for retained applicable denials/revocations |
| 4 | Sorted unique Refs for future-effective authenticated events |
| 5 | Sorted unique Refs for the governing policy/roster/root lineage used to validate this view |

`Ref = [profile:text(1..64 bytes), object_type:uint, canonical_payload_sha256:b32]`.
The profile/object type must be in the provisioned allowlist of existing versions;
no generic decoder fallback or new record allocation. `Artifact = {0: Ref,
1: exact_signed_or_proof_bytes}`. The selected existing profile defines the exact
canonical payload extraction and signature/container verification. Recompute Ref
from those bytes; reject unresolved or ambiguous bindings. Each State reference
must resolve within this response. No URLs, lazy fetches, pagination or delta mode.
The full response remains bounded; a larger deployment requires a reviewed successor
profile, not truncation. Full governance State is distinct from REQUEST fields
10/11; preserve their existing digest rules and explicitly verify the required join.

`Coverage = {0: domain_id:b32, 1: source_id:b32, 2: epoch:u64,
3: revision:u64, 4: source_cut_commitment:b32, 5: covered_through:time,
6: required_evidence_refs:[Ref]}`. Domain/source IDs are exact opaque IDs from
the accepted provisioning policy. Each domain has one explicitly named source
contract defining its ordering, cutoff meaning and cross-domain dependencies;
zero or missing evidence references are allowed only if that approved contract
explicitly relies on the publisher's coverage assertion rather than independent
coverage proofs. The publisher signs both the cut and the claim that no applicable
update through it was omitted. A higher number alone does not establish coverage.

The tuple `(context, domain, epoch, revision)` denotes immutable semantic state,
including a coverage cut and its domain-state commitment. The provisioned source
contract must define how that commitment is obtained and how a later observation
of unchanged records advances the coverage revision/cut. Do not renew an old cut by
changing its timestamp, or compare unrelated source counters as a total order.
All present/future events and dependencies must be jointly consistent under that
contract. Per-domain epochs can change only through authenticated authorized
transitions; not because a source restarted or a counter exhausted.

`state_digest = D(["NBSR-Connector-Currentness-State-draft1", 1,
context_digest, State])`. This commits the whole view separately from request
correlation and response timestamps. For unchanged coverage revisions, state must
remain identical; same-cut contradictions require reconciliation, not last-writer-wins.
A differently correlated wrapper over the same State cannot create a newer cut.

### W4: two independently verified response signatures

The HTTP 200 body is the deterministic CBOR array `[publisher_sign1:bstr,
status_sign1:bstr]`, exactly two elements. Each is a complete tagged COSE_Sign1
byte string. Array packaging is not a governance threshold container; existing
inner Option C records retain their original bytes and quorum verification.

Publisher Sign1 payload:

| Key | Value |
| --- | --- |
| 0 | Literal `NBSR-Connector-Currentness-Response-draft1` |
| 1 | Integer 1 |
| 2 | Request provisioning-context digest, b32 |
| 3 | D(Request), b32 |
| 4 | Request challenge, b32 |
| 5 | PublisherGrant digest, b32 |
| 6 | State |
| 7 | state_digest, b32, recomputed from key 6 and context |
| 8 | issued_at, time |
| 9 | valid_until, time, exclusive upper bound |

Status Sign1 payload:

| Key | Value |
| --- | --- |
| 0 | Literal `NBSR-Connector-Publisher-Status-draft1` |
| 1 | Integer 1 |
| 2 | Same provisioning-context digest, b32 |
| 3 | Same D(Request), b32 |
| 4 | Same request challenge, b32 |
| 5 | Same PublisherGrant digest, b32 |
| 6 | Same state_digest, b32 |
| 7 | authorization_revision, positive u64, in the grant-status authority's own namespace |
| 8 | authorization_state_digest, b32, commitment under that authority's approved state contract |
| 9 | authorization_covered_through, time |
| 10 | issued_at, time |
| 11 | valid_until, time, exclusive upper bound |
| 12 | Literal `authorized` |

The status signer grants bounded use of this publisher key under this grant; it
does not certify State completeness, approve its governing records or change their
authorization. Its revision/state commitment joins the separately retained status
floor; freshness observations advance that revision under its approved source
contract. At one revision the authorization commitment must agree. Only the exact
literal is accepted; an unsigned HTTP refusal is not a signed revocation event.
A positively authenticated contradictory/withdrawn authorization from the separate
approved status-update path disables new use while retaining floors/owned work.
That update path's typed effects must be specified before runtime activation.

### W5: concrete publisher and status-authority authorization

Recommend two dedicated keys with disjoint roles: `connector-currentness-publisher`
and `connector-publisher-status`. The status-authority key is independently pinned
in the commissioning context, must differ from the publisher key, and must not
obtain its authorization/currentness solely from the publisher's snapshot. Key
separation alone does not establish organizational independence; the accepted
commissioning policy must identify operators/control domains and residual risks.
Neither key is reused as a governing-record, transport or client ACP signer in
this profile. Neither role is Federation purpose 14/15, a governance quorum or a
replacement for normal/controller/emergency verification. This is a proposed local role binding,
not permission to add an integer to the frozen purpose registry.

PublisherGrant is a local canonical map inside the independently authenticated
provisioning package, not an independently trusted self-signed wire certificate:
`{0: "NBSR-Connector-Publisher-Grant-draft1", 1: 1,
2: publisher_kid:bstr(1..64), 3: publisher_public_key:b32,
4: Scope, 5: sorted_unique_domain_ids:[b32],
6: not_before:time, 7: expires_at:time, 8: publisher_key_epoch:u64,
9: status_authority_kid:bstr(1..64)}`.
Its digest is `D(PublisherGrant)`. Its acceptance comes from the entire authenticated
commissioning package, not this digest alone. Do not put the enclosing package's
own digest inside the grant: that would create a self-reference cycle.

The bootstrap separately pins the status authority's exact public key, role,
scope/domain policy, validity and independent status-source contract. Its
rotation/removal follows the authenticated commissioning successor procedure;
no network-supplied new kid/key is automatically trusted. This anchor, like initial
root trust, remains an explicit commissioning trust assumption with bounded
validity and independent emergency update/recovery procedures to approve.

On every refresh/startup require the request-bound status signature, not merely
an unexpired long-lived grant. Reject missing, stale, wrong-grant, cross-scope,
revoked or unknown authorization, and preserve previously learned denials. A new
status signature cannot clear a retained withdrawal without the specific approved
recovery/rotation transition. Both signatures must bind the same snapshot and
attempt; a successful refresh cannot be assembled from two unrelated responses.
This separates leaf-key currentness from the leaf's own assertion, but does not
solve dishonest completeness publication or compromise of the commissioning anchor.

### W6: proposed numeric limits and exact freshness tests

All numbers in this table are proposed first-profile limits, not measurements or
claims about a deployed host. Approval must confirm the source/clock/service can
meet them; otherwise revise the draft, never relax limits at runtime to pass.

| Limit | Proposed value / rule |
| --- | --- |
| Entire HTTP request | At most 4096 bytes |
| Entire HTTP response, including both signed objects | At most 65,536 bytes; read/decode bound applies before verification |
| CBOR bounds | Existing maximum depth 16, array items 256, map pairs 128; narrower schema limits still apply; bound embedded-object decoding as part of the same operation |
| State artifacts / coverage domains | At most 64 artifacts and 16 domains in this profile; retained historical safety state has no eviction permission from these per-response limits |
| Concurrent requests / attempts | One outstanding request per scope/context; three attempts per refresh cycle, each with a new challenge |
| Per-attempt deadline | 3 seconds monotonic, including transport, parsing and verification; late completions cannot publish |
| Retry timing / whole cycle | Backoff 0.5 then 1 second; whole cycle at most 12 seconds monotonic; no reset on response/error/hint |
| Clock uncertainty | Verifier interval `[L,U]` must contain trusted UTC and have width at most 2 seconds; unknown/stale clock confidence blocks new use |
| Source ingestion lag | At most 2 seconds from an update's acceptance by its named authoritative source to inclusion at the publisher/status authority; this needs source-contract evidence, not a locally measurable TLS property |
| New response coverage age | `U - C <= 5 seconds`, where C is the minimum of every domain's covered_through and authorization_covered_through; require all cuts <= L |
| Hard coverage lifetime | No use at or after C + 30 seconds, independent of issued_at or re-signing |
| Signature validity window | Each signed valid_until is at most its issued_at + 30 seconds and at most its own minimum coverage cut + 30 seconds; issued_at must be >= its coverage cuts and <= U on verification |
| PublisherGrant lifetime | At most 24 hours; expiry and governing key validity always cap shorter currentness use. Renewal/rotation requires an authenticated successor, not endpoint auto-renewal |
| Regular refresh | Start 8–10 seconds after successful publication (bounded jitter), or earlier to start no later than 5 seconds before the current deadline; coalesce, never overlap |
| Push hints / recovery | Hint only; at most one immediate refresh per second per scope, coalesced. Restart, network recovery, wake or context change schedules validation; none extends the deadline |
| Offline use | Startup: zero. An already verified view: only the remainder of its absolute deadline, at most 30 seconds from C, never an additional 30 seconds after disconnect |

Let `E` be the minimum of both signed valid_until values, C+30, grant expiry,
status-anchor expiry and every applicable governing evidence/policy/key expiry.
New verification must satisfy the coverage-age check, both issuer timestamp rules,
all not-before checks against L and `U < E`. It must also pass a final monotonic
attempt deadline and all authority checks. Availability can be shorter than these
limits; there is no promise that all valid replies will be accepted near a boundary.

At publication save a monotonic deadline no later than `m_now + (E - U)` and the
original signed bounds. Later use requires both the trusted-time bounds and that
monotonic deadline, rechecked at final admission. A clock correction, fresh hint,
retry, unchanged snapshot or same-cut response cannot extend an installed view's
deadline. Extension requires a verified successor with advancing authenticated
coverage in every domain that determines the earliest deadline, plus current
publisher authorization. Still-fresh unchanged domains may be retained only under
their original cuts and limits. There is no scalar "new revision" shortcut.

The 2-second ingestion limit and 30-second coverage lifetime describe different
bounds; they are not proof of instantaneous revocation or a universal 30-second
end-to-end revocation SLA. Typed emergency/controller/normal effects and any
stricter governing expiry remain unchanged. A 300-second emergency ceiling is not
an extension of this freshness window or permission for emergency termination.
If clock/source coverage bounds cannot be established, the result is unavailable
for new registration, not a fabricated fresh observation.

### W7: review and vector gates before implementation

Review this whole profile, especially the added status-authority trust role and
numeric limits, as one proposal. Remaining named deployment decisions are the
actual commissioning/channel provenance, exact per-domain/status source contracts
and canonical commitments, endpoints/transport credentials, approved inner artifact
versions, M3 durable rollback protection and M4 clock implementation. No profile
is deployable with these supplied as unauthenticated placeholders.

Before code or registry changes, freeze a separately reviewed draft artifact and
independent vectors for: canonical request/State/grant/response digests and both
COSE signature domains; every field/type/unknown-key/boundary rejection; altered
scope/kid/grant/context; mismatched paired responses; missing/circular publisher
status; same-cut conflict and re-signing without coverage advance; stale/previous-
boot challenges; exact 5/30-second and L/U/monotonic boundaries; partial domain
coverage and known denial omission; limit exhaustion without eviction; and
interrupted persistence before publication. A reference fixture cannot claim that
an unseen dishonest omission or a real 2-second ingestion guarantee was tested.

No implementation, real credentials, signer generation, runtime/live-trust flags,
READY, Stage 3 closure, commit or push is authorized by this proposal.

### W8: offline literal vectors and measured scope — 2026-11-25

The approved draft now has [108 literal cases](../../vectors/connector-currentness-draft1/vectors.json),
produced by [the deterministic generator](../../scripts/generate_connector_currentness_vectors.py)
and consumed by [a separate fixture checker](../../scripts/verify_connector_currentness_vectors.py).
The generator shares fixture inputs and the existing CBOR/COSE primitives with the
checker, not its expected-outcome decision logic. A separate test directly verifies
both Signature1 transcripts with cryptography and rejects crossed public keys.
This is not a second-language implementation or a production authority verifier.

Observed: 9 positive and 99 negative cases pass; regeneration is byte-identical.
Cases cover malformed/noncanonical CBOR, unknown/missing fields, COSE headers and
signatures, disjoint publisher/status roles, exact scope/context/grant/request/view
bindings, pinned authorization substitution, rollback/conflict fixtures, and time
boundaries at age 5/6, uncertainty 2/3, request deadline 2999/3000 ms, exclusive
expiry and monotonic deadline, 24-hour grant lifetime, plus same-cut refresh without
extension. HTTP size, artifact/domain count and 64-byte kid boundaries have scoped
cases; this is not exhaustive coverage of every combination or all W7 obligations.

The selected test context is explicitly supplied trust. It uses already public
01*32 and 02*32 Ed25519 fixture seeds (also used in existing inclusion fixtures),
not random or real keys. Deterministic Q*32 challenges do not prove live CSPRNG or
pending-request/restart replay state. Nine positives mean `OFFLINE_VECTOR_VALID`,
never registration eligibility. The one inner artifact is the existing purpose-3
KAR positive fixture, independently checked under its retained public root; it is
not a purpose-14 Connector identity or complete governing closure. Fixed cut,
status/floor, clock, anchor/record validity and installed-deadline scenarios are
explicit oracle inputs. No arbitrary source contract or live publisher is verified.

Existing CBOR limits also cap each embedded byte string at 32,768 bytes. Keep this
narrower bound even when the whole HTTP response cap is 65,536; not every body below
the HTTP cap is structurally valid. No global decoder limit was changed.

From the isolated repository root:
```text
python -B -m scripts.generate_connector_currentness_vectors --check
python -B -m scripts.verify_connector_currentness_vectors --check
python -B -m pytest -q -p no:cacheprovider tests/protocol/test_connector_currentness_vectors.py
```
The generator's explicit no-argument mode rewrites only this draft vector file;
`--check` compares without writing. The checker uses public keys only. The
python-protocol CI profile selects the checker and already collects tests/protocol;
its focused selection/execution contract passed locally. No hosted CI was run.

No proof of real completeness/2-second source ingestion, actual clocks, transport,
challenge entropy, atomic persistence, restart recovery, denial retention or
runtime cleanup follows. Existing Docker/authority evidence remains separate.
The source-contract, M3/M4 and real-pilot gates above remain open; no runtime or
frozen registry/source authority is changed by these vector helpers.


## Proposed real-source responsibility and coverage decision — 2026-11-25

Status: proposal for review only. W1–W6 remain the approved draft for offline
vectors; this section selects no deployed operator, endpoint, key or trust anchor.
All real assignments below are **UNSELECTED / UNVERIFIED**. It does not allocate
wire actions or signer purposes, implement a provider, or authorize activation.
The existing artifact mapping remains the implementation inventory.

### S1: recommended real trust sources and role separation

Use independently authenticated commissioning for initial trust, authoritative
issuer feeds for governing records, one scoped publisher for aggregation, and a
separately controlled status authority for the publisher's eligibility. The
Gateway verifies each layer independently; transport success grants no authority.

| Role / real source to select | Required responsibility and evidence | Cannot authorize |
| --- | --- | --- |
| Commissioning custodian, accountable to the deployment's authorized operator | Authenticate the provisioning package and expected digest through a separately authenticated channel; record who approved exact roots, policies, scope, source contracts and status anchor. Identify the actual custodian and recovery authority before import. | A digest from the distribution endpoint cannot authenticate that same endpoint's trust package; commissioning cannot waive governing signatures or create missing delegation. |
| Identity-root and ownership/delegation authorities | Supply the authentic root lineage, purpose-specific KARs, name ownership and non-widening delegation, including revocation/status histories. Bind the actual Connector peer key, operator, service and canonical Gateway ID. | A local allowlist, purpose-3 fixture, DNS/TLS identity or ACP response cannot replace the required purpose-14 transport authorization and signed governing chain. |
| Governing controller / normal / emergency sources | Supply records, authorized rosters, policy versions and authenticated coverage cuts for every applicable authority domain; retain distinct authority modes. | One publisher or one controller cannot replace normal 3/5 or emergency 2/5 verification. |
| Currentness publisher and distribution operator | Operate the W1 endpoint; validate source ingestion, assemble the complete scoped view and sign with the W5 dedicated publisher key under the exact PublisherGrant. Record distribution operator separately even if hosted by the publisher. | Neither endpoint TLS nor the publisher signature creates governing authority or proves unseen updates were not withheld. |
| Publisher-status authority | Under the independently provisioned W5 anchor, maintain a separate grant/key-epoch eligibility ledger and sign request/view-bound status from that ledger. Its administration and withdrawal path must not depend on the publisher. | Status means publisher eligibility only, not complete revocation coverage, registration permission or a governance quorum. |
| Gateway verifier / local state custodian | Independently verify the full chain, source contracts, coverage, status, time and persisted safety state before admitting new use. Retain ownership until confirmed cleanup. | A valid snapshot cannot clear durable denials, bypass uncertain persistence or replace missing source evidence. |

Recommend separate administrative control for commissioning/recovery and online
publication, and for publisher-status administration and publication. Record actual
people/organizations, control domains, key custody and shared dependencies before
calling that separation independent. Different key IDs or containers alone are
insufficient. Existing governing roster independence requirements still apply;
these operational assignments add no new quorum or frozen-purpose allocation.

### S2: source coverage required for the real deployment

Commissioning must enumerate the exact required domain set and the authoritative
source for each domain. The publisher cannot choose a smaller set at refresh time.
A source may cover several domains only when its authenticated authority and
coverage contract explicitly cover each one. The following is a requirements
matrix, not a claim that these feeds already exist:

| Coverage domain | Required source material and boundary | Retained effect / rejection condition |
| --- | --- | --- |
| Root, key and governing configuration lineage | Authorized root/policy/roster succession and status for every signer and dependency used in the view, including unsigned roster members where independence is required. | Unknown lineage, revoked signer or an unapproved version blocks acceptance; no current-registry fallback for historical authority. |
| Connector identity, ownership and delegation | Complete applicable KAR, ownership and delegation state plus withdrawals affecting the exact peer/operator/service/Gateway dependency closure. | Exact purpose and non-widening scope checks remain mandatory; unrelated records cannot revoke an owner merely by naming it. |
| Controller revocation | Applicable controller-signed typed records and their source coverage, under the existing exact-controller authority rules. | Apply only verified typed effects; controller-only coverage is not full-model coverage. |
| Normal revocation | Applicable records with the approved normal 3/5 authorization, roster provenance and required inclusion/consistency evidence. | Do not substitute global-trust-v1 for normal-revocation policy; preserve effective termination and retained denial markers. |
| Emergency revocation | Applicable emergency 2/5 records and coverage under the approved emergency authority policy. | Nonterminal DENY_NEW_USE only, at most 300 seconds; no emergency termination or extension of freshness deadlines. |
| Publisher authorization | Independent status ledger covering the exact grant, publisher key/epoch and scope, including withdrawals and approved recovery transitions. | Missing/stale/unknown status blocks a fresh acceptance. An ordinary authorized response cannot erase a retained withdrawal. |

For each row, the real source contract must name the source identity and operator,
exact accepted artifact/profile versions, authenticated epoch/revision ordering,
cut commitment semantics, scope enumeration, and how the verifier establishes
that no applicable accepted update through the cut is omitted. Specify initial
history acquisition, gaps, duplicates, forks, epoch transitions and cross-domain
dependencies. Required evidence must fit the bounded complete W3 view; oversized
or incomplete results reject rather than truncate or silently paginate.

An inclusion proof establishes inclusion of a record, not the absence of omitted
records. A checkpoint or witness signature establishes only its specified claim;
it is not automatically a completeness attestation. A successful poll, empty HTTP
response or locally increasing counter cannot advance authenticated coverage.
Sources must distinguish “no updates through this authenticated cut” from outage.

Recommend an authenticated source-side acceptance journal and explicit coverage
attestation for each domain, with independently checked ingestion/cut consistency.
The actual attestation schema, issuer authority, commitment construction and
verification rules remain an approval prerequisite; this section creates none.
If a source cannot supply that evidence, the commissioning decision must explicitly
accept and bound the W3 publisher-completeness trust assumption or leave that
source unusable. Offline vectors do not resolve this choice. No configuration
switch or fallback to an unverified partial view is proposed.

Coverage means all applicable updates accepted by the named source through its
cut, not immediate knowledge of every real-world event. Establish the source's
submission/acceptance boundary and measured ingestion evidence before accepting
the proposed 2-second lag bound. Retain future-effective records and prior denials;
a newer unrelated cut cannot extend an older domain's lifetime. Existing work
continues only under its independent authority/request/drain bounds, with verified
applicable termination taking precedence and no grace reset on repeated outage.

### S3: independent status withdrawal and recovery responsibility

The status authority reads its own authorized grant/key eligibility ledger, not
a boolean supplied by the publisher. Before it signs “authorized”, it must bind
the W4 request, grant and state digest and check current eligibility. Binding a
state digest does not certify that state's completeness. Publisher delivery may
carry the status proof; administration and trust provenance remain independent.
Suppression can cause loss of availability but cannot extend the W6 deadline.

Before activation, approve a separate authenticated withdrawal/update path,
including who may withdraw a grant, exact typed scope/effects, replay ordering,
retained markers and how Gateway state persists them. Do not invent a negative
variant of W4's authorized-only response. Define an independently authenticated
recovery/rotation transition; a new signature or epoch alone must not resurrect
a withdrawn grant or erase governing denials.

Status-anchor compromise/expiry is handled by the independently authorized
commissioning successor/recovery procedure, never by trusting a replacement key
announced solely by that anchor or publisher. Record the recovery actor and its
independent authorization evidence. If unavailable, fresh acceptance stays blocked;
already accepted state cannot outlive its existing effective deadline. This is a
remaining design/operational dependency, not an implemented update service.

### S4: concrete evidence needed to replace UNSELECTED assignments

Before any separately authorized pilot, complete one commissioning record in this
existing decision trail with:

1. Named accountable operators for each S1 role, control-domain relationships,
   and approval of the chosen completeness trust assumption or per-domain proof.
2. Exact public root/status/publisher fingerprints, grant and package digests,
   validity, scope and the independent channel used to authenticate them. Keep
   private keys, credentials and recovery secrets out of this document and chat.
3. The real distribution/status/source endpoint identities and their transport
   authentication policies, without deriving trust from endpoint discovery.
4. A source contract and authenticated sample history/cut for every required
   domain, including actual controller, normal and emergency coverage and signer
   lineage. Record unavailable feeds as blockers, never as empty revocation sets.
5. Approved publisher withdrawal and status-anchor recovery procedures, plus M3
   independently anchored durable restart state and M4 trusted clock/serialized
   runtime verification. A restored pair of mutually consistent local files alone
   does not establish anti-rollback protection.
6. A scoped implementation and later pilot acceptance plan: full positive chain,
   missing-domain/stale/fork/withdrawal negatives, restart/rollback and cleanup
   failure retention, with exact source versions and redacted evidence retained.

No real assignments or authenticated source samples are established by this
proposal. Next is selecting and reviewing those sources/contracts, then implementing
and testing the approved boundary offline before separately authorizing a real
pilot. The existing vectors prove only their draft fixture behavior; Stage 3 stays
open until real registration, current authority and lifecycle evidence satisfy
its acceptance gates. No activation, READY, commit or push follows from this text.


## Draft real-source contracts by domain — 2026-11-25

The S1–S4 direction is user-approved for further drafting. The contracts below
are proposed acceptance requirements, not executed agreements or newly approved
wire formats. Actual source identities, operators and proof mechanisms remain
UNSELECTED / UNVERIFIED. C1–C6 are document labels, not allocated domain IDs.
Preserve W1–W6 and every existing governing signature, purpose and typed effect.

### Common contract required for each source

Each commissioned source contract must contain the following independently
authenticated bindings. An omitted required binding makes that source unusable
for fresh acceptance; it is never interpreted as an empty revocation set.

| Binding | Contract requirement | Still undefined for the real deployment |
| --- | --- | --- |
| Identity and authority | Bind source ID, domain ID, accountable operator, control domain, exact public signer keys/purposes, authority lineage and accepted artifact versions. Distinguish feed attestation authority from authority to issue governing records. | All concrete identities, keys, authorization evidence and selected versions. |
| Scope and closure | Bind the exact commissioned scope, dependency classes, governing issuers and selection rule. Include every applicable dependency and authority mode, with no publisher-controlled narrowing. | Concrete scope inventory and independently reviewable dependency enumeration. |
| Acceptance boundary | Define when a valid submission becomes an accepted source update, how the issuer receives an authenticated receipt, and how effective time differs from acceptance time. Include accepted future-effective updates. | Receipt schema, issuer/source responsibility and handling of delayed submissions. |
| Ordering and cut | Define authenticated epoch/revision ordering, immutable cut commitment and covered-through time; identify exactly which accepted updates the cut covers. Same cut with different state is a conflict, not a refresh. | Cut/commitment construction, signed encoding and verification algorithm. |
| Completeness | Supply verifiable coverage for the full scoped accepted history through the cut, including authenticated zero-update intervals. State the remaining trusted omission assumption explicitly. Inclusion or consistency alone is insufficient. | Per-domain coverage proof or explicit approval of the bounded publisher-completeness assumption. |
| Delivery and resumption | Identify authenticated endpoint/transport policy, bounded complete-view production, gap detection and replay from retained anchors. No truncation, unsigned empty-success or automatic alternate source. | Endpoints, credentials provisioning procedure, resumption protocol and source capacity evidence. |
| Time and availability | Supply authenticated cut times and evidence supporting W6's proposed ingestion/freshness bounds. Outage cannot advance a cut or restart an existing deadline. | Trusted source clock basis, measured lag, monitoring and accountable incident operator. |
| Succession and recovery | Authenticate key/epoch/source changes through approved lineage, preserving retained denials and floors. Do not treat a replacement source as a pristine history. | Exact migration, compromise, withdrawal and recovery procedures and authorized actors. |

Source receipt time, publisher ingestion time and Gateway observation time must
remain separate in evidence. A source cannot claim that an accepted update is
outside its coverage merely because downstream delivery failed. Updates not yet
accepted by the named source remain outside that coverage claim; the submission
boundary and its availability risk must be visible to commissioning reviewers.

### C1: root, signer and governing-configuration status

**Input:** authenticated trust-root succession, signer authorization/status,
roster and policy lineage for all dependencies used by C2–C6. Include roster
members needed for independence checks even when they did not sign this record.
**Coverage obligation:** enumerate the exact root/configuration versions and all
applicable withdrawals or status changes accepted through each cut. Verify each
record under its own applicable historical authority, without current-registry
fallback or replacing immutable pins.
**Failure behavior:** unknown lineage, an unauthorized version or missing status
blocks dependent fresh acceptance. A higher configuration revision does not erase
prior denials. An authorization cycle must resolve to independently commissioned
anchors; a source cannot bootstrap its own authority from its own status response.
**Unresolved:** real root custodians, accepted successor profiles, source inventory,
anchor validity/recovery and coverage attestation authorization.

### C2: Connector key, ownership and delegation revocation

**Input:** the actual Connector peer's purpose-14 KAR and applicable ownership,
delegation and bilateral authorization chain under existing purpose rules.
**Coverage obligation:** bind the exact operator, service, peer key and canonical
Gateway ID; cover all applicable key revocations, ownership changes, delegation
withdrawals and governing dependencies through authenticated cuts. A local
allowlist only narrows signed authority. Reuse the approved dependency semantics;
do not define new ownership-transfer effects in this feed contract.
**Failure behavior:** missing chain/status rejects fresh acceptance; an unrelated
record cannot acquire effect solely by naming an owner. Apply authenticated,
applicable negative effects under their existing typed lifecycle rules.
**Unresolved:** real issuer/delegation sources, registration action allocation,
concrete dependency closure and an authenticated complete status feed for it.

### C3: controller revocation

**Input:** typed controller records authenticated against the exact governing
controller and scope, together with C1/C2 provenance as applicable.
**Coverage obligation:** include every applicable controller update accepted
through the declared cut, including scheduled future effects and retained denials.
Controller coverage must be separately identifiable even if transported beside
normal and emergency records.
**Failure behavior:** reject forged, cross-controller or out-of-scope effects;
missing coverage blocks a new complete-view acceptance. Controller coverage never
substitutes for C4 or C5. Already verified applicable negative effects retain their
existing enforcement semantics despite another domain's outage.
**Unresolved:** controller identity, source endpoint, exact coverage commitment
and source-side evidence of accepted submissions and complete intervals.

### C4: normal revocation

**Input:** typed normal records meeting the approved normal 3/5 authorization,
exact signer purposes, roster independence and governing configuration provenance;
include required record inclusion and checkpoint/consistency evidence under the
explicitly selected approved profile.
**Coverage obligation:** enumerate all applicable accepted normal records, their
original authenticated bytes and effective times, without omitting already applied
records or future events. Keep exact event bindings and retained denial markers.
**Failure behavior:** global-trust-v1 is not a substitute for normal-revocation
policy. Valid inclusion of selected records cannot establish complete coverage.
Verified applicable termination retains its precedence; cleanup failure retains
ownership/quota until exact successful confirmation.
**Unresolved:** real five-member roster and control domains, accepted record/proof
profile, log/witness sources where required, and complete-interval attestation.
No new universal witness requirement is introduced here.

### C5: emergency revocation

**Input:** typed emergency records with the approved emergency 2/5 authorization,
exact scope, authorized roster and C1 provenance.
**Coverage obligation:** cover all applicable accepted emergency events, including
future-effective events, and preserve the information needed to distinguish expiry
from replay or a different event. Do not infer absence from an expired latest record.
**Failure behavior:** preserve nonterminal DENY_NEW_USE and the 300-second maximum;
no emergency termination, implicit renewal or extension of W6 freshness. Emergency
expiry cannot clear independent controller/normal denials. History compaction, if
needed, requires a separately justified safe retention rule; size limits do not
authorize eviction of safety state.
**Unresolved:** emergency roster/source, activation and expiry evidence, coverage
proof and authenticated recovery semantics under the existing governing policy.

### C6: publisher-grant and publisher-key status

**Input:** W5's independently commissioned status anchor, exact PublisherGrant,
key epoch/scope and the status authority's independently administered ledger.
**Coverage obligation:** cover eligibility changes and withdrawals of that grant
and key through the status cut. Return W4's request/view-bound authorized proof
only when current eligibility is established; publisher assertions are not ledger
inputs sufficient to authorize themselves. C6 does not attest C1–C5 completeness.
**Failure behavior:** unavailable, stale or unknown status blocks fresh acceptance.
Retain verified withdrawals; a newer authorized response alone cannot erase them.
The separately approved withdrawal path must define authenticated typed effects;
this contract does not add a negative W4 wire message. Anchor compromise follows
independent commissioning recovery, never self-announced replacement trust.
**Unresolved:** status operator/key/ledger, who authorizes withdrawal and recovery,
its delivery/typed-proof format, anchor succession and durable retained markers.

### Joining the contracts and recording acceptance

The commissioning package must pin the exact contract versions and required domain
set. Those version bindings are conceptual requirements pending package schema
approval, not new implicit W3 fields. Each W3 coverage entry must map unambiguously
to its approved source contract; changing a source or contract requires authenticated
context succession and invalidation of old in-flight attempts.

A complete candidate view must satisfy every required domain and cross-domain
configuration/dependency binding. Different cut times are allowed only within W6
bounds; they do not excuse a combination that omits a dependency needed by another
record. If consistent closure cannot be established, reject the candidate rather
than mixing unrelated latest records. Valid applicable negative evidence must
remain processable through its approved typed path even when positive acceptance
is blocked; partial coverage does not create positive authority.

Before any contract is accepted for a pilot, retain its authenticated sample
history and expected results for: an empty interval, an accepted update missing
from a view, a gap/fork, same-cut conflict, future-effective event, stale cut,
source outage, unauthorized succession and restart with retained denials. C3–C5
also need authorized and unauthorized mode-specific records; C6 needs withdrawal
and rejected resurrection. Proposed cases are not test results. Independent durable
floors (M3), trusted clock/runtime enforcement (M4), real source selection and a
reviewed wire/proof definition remain open. Stage 3 remains open; this document
change activates nothing and provides no READY, commit or push authority.


### Offline six-domain coverage vectors — 2026-11-25

The contract direction above is approved for offline vectors only. The retained
package is [connector-source-coverage-draft1](../../vectors/connector-source-coverage-draft1/vectors.json),
with a [generator](../../scripts/generate_connector_source_coverage_vectors.py),
a [separate checker](../../scripts/verify_connector_source_coverage_vectors.py)
and [focused tests](../../tests/protocol/test_connector_source_coverage_vectors.py).
The generator does not call the checker to choose expected results.

The 92 literal cases comprise 8 positives and 84 negatives. Positives cover a
complete six-domain snapshot, a known empty interval for each individual domain,
and a known empty interval across all six domains. Each domain has 14 negatives:
missing domain, omitted record, empty response, wrong source, wrong contract,
rollback, same-cut conflict, stale cut, unsupported future cut, boolean revision,
lost denial, lost future event, injected failed record verification and source
outage. Additional unit checks cover cross-domain substitution, duplicate records,
unknown epoch/cut, malformed fields and lost retained restart markers. Rejected
checks must leave their input and retained state unchanged.

This is a bounded coverage-bookkeeping model. C1 through C6 are symbolic fixture
labels, not wire allocations. Each domain's supplied history contains one retained
denial and one future event; two trusted oracle cuts describe the same history
before and after an empty interval. Commitments are symbolic strings, not hashes
or authenticated source attestations. Injected inner-verifier results stand in
for root/lineage, identity/delegation, controller, normal 3/5, emergency 2/5 and
publisher-status verification respectively. These tests do not execute those
cryptographic verifiers or prove their typed effects, emergency timing, source
acceptance/ingestion, cross-domain governing closure, recovery or durable restart.
The fixed clock and retained snapshot are explicit inputs, not trusted runtime
services. No private/public key generation, signing, sockets or Docker is used.

`OFFLINE_COVERAGE_VALID` means only that a view matches the supplied coverage
oracle. It can contain retained denials and is never admission eligibility or
READY. The earlier currentness wire/signature vectors remain separate and unchanged;
combining two fixture suites does not establish a real authority provider.

From the isolated repository root, using the provisioned Python environment:
```text
python -B -m scripts.generate_connector_source_coverage_vectors --check
python -B -m scripts.verify_connector_source_coverage_vectors --check
python -B -m pytest -q -p no:cacheprovider tests/protocol/test_connector_source_coverage_vectors.py tests/protocol/test_connector_currentness_vectors.py tests/ci/test_ci.py -k "not connector_docker_supervisor"
```
The generator's no-argument mode writes only the new package; `--check` compares
without writing. CI's python-protocol profile selects the checker and collects
its tests through tests/protocol. The local selection check runs the offline
checker only. Hosted CI and real source coverage remain unverified; no contract
proof format or production protocol is approved by these artifacts.


## Stage 3 provider-to-registration integration proposal — 2026-11-28

Status: proposed for review before implementation. This appendix connects the
existing M1/M2, W1–W8 and C1–C6 sections; it does not replace them or approve their
remaining runtime/deployment decisions. Inspection baseline:
`97542f654656a1286627dc4a87ad9a3cd0dbeed2`. No runtime, wire allocation, READY,
Stage 3 closure, real source commissioning or publication is authorized here.

### Existing implementation seams and proposed ownership

| Existing seam | Proposed connection | Boundary to preserve |
| --- | --- | --- |
| `deploy/single-instance/validate_config.py`: `trust_ref`, `registration_policy_ref`, `registration_authority_ref` | A separately reviewed provisioning consumer resolves and authenticates the references according to M1 and the source register below. | The current validator remains side-effect-free and reports `CONFIG_VALID_OFFLINE`; it must not open references or turn configuration validity into readiness. |
| `client/nbsr-go-client/internal/authority/http_provider.go` and `restart.go` | Reuse bounded transport and fresh-start/persist-before-publication patterns where applicable to W1 and M3. | These are Go client mechanisms, not a Rust connector provider. Reuse the design and conformance cases; do not import ACP operations, purposes 15/16, client identity or a Go internal package into connector governance. |
| W1–W8 currentness draft and its existing checker | A destination-side verifier authenticates the paired publisher/status response, all inner dependencies, source coverage and retained state. | The fixture checker is a reference for the draft, not a production verifier or permission to trust injected verdicts. The actual transport and production module placement remain implementation-review decisions. |
| `crates/nbsr-transport/src/connector_registration.rs`: `Authority::verify`, `revision`, challenge/proof revalidation | A sealed verifier-owned view supplies an attempt-specific authority result; the registration owner rechecks it at final commit. | This module is test-only. Its publicly constructible `Decision` is not the future runtime API; no caller may manufacture a positive result. |
| `crates/nbsr-transport/src/connector_authority.rs` and existing cleanup ownership | Reuse validated typed negative enforcement and exact cleanup-ticket ownership under the same serialized coordinator. | `registration_ready()` remains false. Normal negative enforcement under supplied trust does not establish complete positive authority or all governing modes. |
| `interop/nbsr-go-peer/connector/coordinator.go` and the Go/Rust loopback harness | Reuse the existing request/proof/renewal and owned transport lifecycle once the destination authority boundary is approved. | Connector-side checks and TLS/exporter proof cannot replace destination authorization. Replacing `SyntheticAuthority` alone is not Stage 3 acceptance. |

Proposed flow, without a new wire field or API commitment:

```text
Authenticated provisioning + commissioned C1–C6 source contracts
    -> bounded currentness fetch (W1–W6)
    -> independent signature / dependency / coverage / time verification
    -> serialized recheck and durable safety-state commit (M3/M4)
    -> immutable verified view, never a registration permit
    -> exact registration-attempt binding and final revalidation
    -> existing registration ownership / acceptance or rejection
```

The adapter joins the existing `Binding` fields (profile/action, connection,
session, peer, service, canonical Gateway text ID, operator, request digest,
dependency digest and policy) with the exact operation counter and current view.
The counter stays in its existing operation namespace; it is not a new Binding
or wire field. Admission must complete within the applicable authority,
currentness, policy, challenge and request deadlines. The challenge deadline
bounds proof completion, not the lifetime of an accepted registration. Registration
lease and admitted-work lifetime retain their existing independent authority,
renewal and drain rules; this appendix does not shorten or extend them. View
validity alone does not mean eligibility: an authentic complete view can contain
an applicable denial.

Final admission must recheck context, revision, time, outstanding attempt and
cancellation under the same serialized ownership boundary. Context succession,
expiry or a revision change invalidates a stale completion. The network fetch
must not hold that ownership boundary; only a bounded verified candidate reaches
publication. Higher floors and retained events are committed before publication;
uncertain persistence blocks new use and preserves ownership. Startup restores
safety state, never a live permit or pending challenge. Existing M2 failure rules
continue to distinguish invalid input, freshness loss and authenticated typed
negative effects; already verified negative evidence remains processable while
positive admission is blocked. No refresh may restart work grace or clear denials.

### Source and evidence register: initial unfilled deployment record

This register instantiates S4's tracking requirement without repeating the source
contracts. C1–C6 remain document labels, not wire domain IDs. `UNSELECTED` means
no accepted deployment assignment is recorded here; `UNVERIFIED` means no
qualifying authenticated evidence is linked here. Neither means an empty history
or proof that an external source cannot exist. Existing fixtures do not fill a row.

| Record | Existing contract to satisfy | Accountable real source / custodian | Qualifying evidence reference | Current state |
| --- | --- | --- | --- | --- |
| Commissioning and recovery | M1, W5, S1/S4: independent package authentication and authorized succession | UNSELECTED | UNVERIFIED | Blocks trust import |
| C1 | Root, signer and governing-configuration status | UNSELECTED | UNVERIFIED | Blocks complete-view acceptance |
| C2 | Connector key, ownership and delegation revocation | UNSELECTED | UNVERIFIED | Blocks complete-view acceptance |
| C3 | Controller revocation | UNSELECTED | UNVERIFIED | Blocks complete-view acceptance |
| C4 | Normal revocation, including the existing 3/5 requirements | UNSELECTED | UNVERIFIED | Blocks complete-view acceptance |
| C5 | Emergency revocation, including the existing 2/5 and bounded nonterminal effects | UNSELECTED | UNVERIFIED | Blocks complete-view acceptance |
| C6 | Publisher-grant/key eligibility and independent status authority | UNSELECTED | UNVERIFIED | Blocks complete-view acceptance |
| Publisher / distribution | W1, W4/W5, S1/S2: aggregation, source ingestion and completeness responsibility | UNSELECTED | UNVERIFIED | Blocks authenticated currentness |
| M3 state custodian | Independent recovery anchor, durable floors, retained denials/events and uncertain-write reconciliation | UNSELECTED | UNVERIFIED | Blocks safe publication/restart |
| M4 clock / coordinator | Reviewed uncertainty source, monotonic failure latch and serialized event/admission commit | UNSELECTED | UNVERIFIED | Blocks timed runtime acceptance |

For each selected row, attach an immutable evidence record containing: accountable
operator and control-domain relationships; exact scope and source-contract version;
public signer fingerprints/roles and authorization lineage; package/grant/artifact
digests and validity; independently authenticated provisioning provenance; and the
applicable accepted-history/coverage-cut evidence. Record transport identity and
policy by an operator-owned reference, not by placing private endpoints or
credentials in this public document. C6 also requires independent withdrawal and
recovery evidence. M3/M4 use their recovery/time evidence instead of pretending to
be governing feeds. Keep secrets, private keys and raw credentials out of both
this register and test logs.

Each evidence record must distinguish proposed, supplied and verified material,
name its reviewer and record the exact source revision, verification command,
result and limitations. Source selection or passing fixture tests cannot mark a
row accepted. Acceptance requires its existing contract's evidence and explicit
review; changes require authenticated succession, retained history and invalidation
of old in-flight attempts. Cross-reference shared evidence rather than copying it
across rows; shared hosting does not establish independent control.

### Smallest next deliverable and acceptance boundary

Before implementation, fill/review the source assignments and choose the still-open
completeness, M3 and M4 mechanisms identified above. Reuse the existing W7 and
C1–C6 acceptance matrices. Their supplied-trust and symbolic coverage suites remain
separate historical evidence; do not create another equivalent vector package.

The later adapter-specific checks should cover only the missing composition:
valid full evidence plus exact request binding; a wrong service/peer/session or
counter; a view changed between challenge and proof; cancellation or late fetch;
uncertain persistence before publication; fresh restart with retained denials;
and applicable negative enforcement while refresh is unavailable. Assert that a
failed registration attempt creates no registration or dispatch for that attempt.
Rejected unrelated input must not invalidate an existing verified view or owner;
a refresh transport error alone must not revoke still-valid authority. Test
freshness expiry, uncertain-persistence blocking and authenticated typed negative
effects separately under M2. Existing work keeps its independent bounds, with no
ownership release without confirmed cleanup.
Reuse existing codec/signature, registration and cleanup tests for their own
boundaries. Test results, source evidence and later real loopback acceptance must
be recorded separately; none is claimed by this documentation-only proposal.
