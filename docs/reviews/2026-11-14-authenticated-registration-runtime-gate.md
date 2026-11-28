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


## Six-domain reconciliation with approved WP8 decisions - 2026-11-26

This mapping refines the unresolved lists in S1-S4 and C1-C6; it does not reopen
approved governance or promote the new currentness draft into a frozen profile.
Read "unresolved" in those lists as the concrete deployment binding, missing
proof specification or unproven runtime implementation identified below, not as
absence of the underlying WP8 requirement.

### Authority and precedence

The detailed [approved WP8 source](../protocol/history/NBSR-WP8-F1-F119-approved-source.txt)
is the historical authority: 318,890 bytes, SHA-256
`6058485d07d9c827c0cb62dad325fb389b213e35801c0799414bb6338d89848e`,
verified for this read-only reconciliation. Use the exact titled decisions below:
the condensed F-number index is navigation only and some of its summaries do not
match the historical numbering (for example historical F55 is rollback protection).
The [direction register](../protocol/wp8-federation-v0.1-direction.md) defines
precedence: later approved profile amendments govern only their explicit scope.
Neither the historical source nor its immutable registries are edited here.

| Contract | Existing decision authority to reuse | Actual remaining gap |
| --- | --- | --- |
| C1: roots, signers and governing configuration | Historical F9, Offline Root/Purpose-Bound Operational Keys; F15, Root-Signed Key Authorization Records; F47, Canonical Scoped Trust Bundle Contents; F48, Scope Authority Signs the Trust Bundle; F49, Automated Reconciliation; F53-F55, version/continuity/rollback; F60, Transparency-Verified Trust Bundles. Root custody, scoped signer authority and safe succession are already requirements. | Select the actual roots, scoped authority, public keys, accepted configuration lineage and applicable proof profiles; authenticate their initial provenance. Implement the existing rules at the Connector runtime boundary. Define how the currentness view proves complete relevant configuration/status coverage. |
| C2: Connector key, ownership and delegation | Historical F15-F23 establish root-authorized keys, registry-rooted ownership, explicit narrowing delegation, acyclic chains, validity, revocation and continuity. F86 explicitly includes independently revocable Origin Connectors and dependency-directed effects. The current Development Profile signer matrix and approved Connector mapping supply exact purpose/scope constraints. | Bind the actual peer key, operator, service and Gateway to authenticated records; resolve the Connector registration action/profile allocation still named by its runtime gate. Supply the full relevant chain and coverage feed. Do not redesign ownership or delegation. |
| C3: controller revocation | Historical F86, Typed Revocation Across All Trust-Critical Object Classes; F87, Reason-Dependent Terminal Revocation; F88, Permanent Terminal Tombstones; F93, Severity-Based Existing-Session Enforcement. The Development Profile explicitly selects target-controller 1-of-1 as an authority alternative. | Identify and authenticate the exact target controller and its live record source; compose existing typed verification with coverage and runtime enforcement. Missing source coverage is not permission to replace the full model with controller-only operation. |
| C4: normal revocation | F86-F88 and F93 define target/dependency/enforcement behavior. The Development Profile defines normal 3-of-5; the separately approved normal-revocation revision-2 local amendment supplies the precise normal policy mapping and full-roster independence checks. F35-F44 and F60 supply applicable transparency principles. | Authenticate the real roster/control domains and governing context; approve/select live packaging and applicable log/witness evidence, then implement the runtime decoder/composition. The local amendment is not live authorization. Prove complete coverage in addition to inclusion of individual records. |
| C5: emergency revocation | Historical F58, Immediate Revocation with Automated Emergency Key Replacement; F59, Pre-Authorized Threshold Break-Glass Recovery; F118, Risk-Based Authority and Witness Thresholds. The Development Profile and current Connector contract retain the specific emergency 2-of-5, nonterminal deny-only alternative. | Bind the actual emergency roster, source and authenticated events to the existing typed policy and timers. Establish complete coverage and recovery provenance. Do not infer that emergency signers can authorize replacement roots/keys or permanent termination from the general automation language in F58. |
| C6: publisher grant/key status | F9/F15 already require purpose-bound authorized keys; F47/F48 define scoped trust material and its signer; F49 defines policy-controlled publication from approved signed desired state; F58/F59 and F86 cover compromise/recovery and exact-key revocation principles. These constrain the proposed publisher and status roles. | The dedicated currentness publisher/status roles, PublisherGrant and request/view-bound status receipt are a newer draft, not an existing WP8 allocation. Their exact authorization mapping, independent status source, withdrawal proof and recovery transition still require approval and implementation. F49's reconciliation controller does not automatically possess any of those signing authorities. |

For C2/C3/C4/C5, consult the
[Development Profile signer-authority matrix](../protocol/federation-v0.1-development-profile.md#signer-authority-matrix-and-cose-kid-binding)
and its machine authority, not an inferred threshold from a similarly named
policy. In particular, the
[normal-revocation amendment](2026-10-11-normal-revocation-conformance.md)
is distinct from global-trust-v1: sharing 3-of-5 does not make their signers,
purposes, scope or evidence interchangeable. Its local conformance approval does
not authorize a runtime source overlay or change historical Option C defaults.

### Cross-domain obligations already decided

- **Trust inventory and distribution:** F47 already requires roots, keys, logs,
  witnesses, revocation references/endpoints, validity and scope in the bundle.
  F48 decides which authority may sign for each scope. F49 already specifies
  reconciliation, publication, distribution and guarded activation. Actual endpoint
  addresses, operators and commissioned public keys are deployment inputs still
  to supply; their absence is not a missing architectural decision.
- **Continuity and restart:** historical F54 requires hash-linked continuity;
  F55 requires the highest accepted generation/sequence/digest and revocation
  state to survive restart, replacement, cache loss and failover. M3 is therefore
  an implementation/evidence gap: choose and prove an allowed durable or externally
  authenticated recovery mechanism. It is not a new decision on whether rollback
  protection is required. Missing local state cannot imply pristine enrollment.
- **Freshness and outage:** historical F57 and F89-F92 require bounded,
  risk-specific freshness/outage behavior and fail-closed new authority when the
  bound is exceeded. W6's tighter numbers are a Connector draft profile proposal,
  not replacements for existing Federation timing values. Approve the exact
  profile relationship and prove clock/ingestion/runtime behavior under M4.
- **Completeness:** F42/F44 establish consistency and witnessed checkpoint roles;
  F86 establishes typed revocation across dependencies. These do not by themselves
  specify a proof that a Connector snapshot contains every relevant accepted
  update through a cut. The C1-C6 source acceptance boundary, coverage commitment,
  cross-domain closure and explicitly bounded omission-trust assumption remain
  genuine specification gaps. Do not invent a completeness claim for witnesses.
- **Scope of governance:** historical F48/F118 and the final profile distinction
  permit explicitly scoped private/consortium deployments without claiming global
  governance. Public/global institutional requirements are not a prerequisite to
  development. That distinction does not select a new private profile here or
  waive the current Connector's controller/normal/emergency obligations.

### Narrow remaining work

1. Fill the deployment bindings already required by WP8: selected scope/profile,
   accountable operators, independently authenticated public roots/keys, exact
   endpoints, real rosters and governing source/proof versions for C1-C6.
2. Resolve only the new contracts: complete-currentness evidence and source cuts,
   dedicated publisher/status authorization and withdrawal/recovery, plus exact
   Connector action/profile and timing mappings still pending at the runtime gate.
3. Implement and verify those bindings with existing verifiers, M3 persistence,
   M4 clock/serialization and lifecycle cleanup; then obtain separately authorized
   real-source pilot evidence. Fixture passes do not satisfy these runtime gates.

No new global governance redesign, universal witness policy, threshold reduction
or controller-only fallback is proposed. This reconciliation changes documentation
only; it grants no activation, READY, commit, push or Stage 3 closure authority.


## Remaining authority gaps: execution plan for review - 2026-11-26

**Goal:** obtain authenticated, complete and current real-source registration
with nonregressing restart state and confirmed lifecycle cleanup, under the
existing WP8 decisions and the Connector acceptance gate.
**Spec:** the six-domain WP8 reconciliation immediately above, C1-C6, M1-M4 and
the existing Stage 3 acceptance requirements in this document.
**Architecture:** scoped commissioning establishes trust; independently verified
source evidence supplies governing state; the Gateway composes currentness,
persistence and time checks before the serialized owner transition. Publication
and status signatures cannot replace governing authorization.
**Tech stack:** existing Python reference verifiers and fixtures, the development
Rust Gateway and Go Connector; no new dependency or deployment choice is made here.
**Execution:** after separate authorization, use the executing-plans workflow
sequentially, one bounded task and focused review at a time. This is a proposed
plan, not permission to execute it or a declaration that its outputs exist.

### Global constraints and dependencies

Preserve frozen registries, approved signer purposes and all applicable
controller/normal 3-of-5/emergency 2-of-5 obligations. No controller-only fallback,
implicit new signing purpose, automatic trust discovery or partial-view admission.
Keep the historical fixtures and their limits intact. Every implementation step
starts with a failing focused regression, then the smallest change, affected tests
and one scoped review; add its checks to the affected CI profile. Commits/pushes
require their own task authority. Use provisioned dependencies and existing resource
guards; live sources, sockets/test PKI, ACL changes and pilot execution need their
applicable action-time scope. Do not touch the original checkout or unrelated Docker
resources. Document approval does not change runtime flags or registration_ready().

Dependency order: **P1 -> P2 -> P3 -> P4 -> P5 -> P6**. P1 may record missing
services, but P2 cannot declare real source bindings complete until they exist or
an explicitly scoped implementation deliverable is selected. P4's storage and time
contracts may be drafted during P2; no integration acceptance skips P3 or P4.

### P1 - Populate the actual commissioning inventory

**Responsible role:** deployment owner supplies assignments; implementer checks
bindings against WP8 F15/F47/F48 and the C1-C6 contracts. Actual people remain TBD.
**Document:** extend this existing record; do not create a competing trust policy.

- [ ] For each of C1-C6, record actual scope/profile, source operator, source ID,
  public key/fingerprint and purpose, authority chain, contract version, endpoint
  identity, dependency set and required log/witness/roster references.
- [ ] Mark each source as existing with retained provenance, available but not
  authenticated, or absent and requiring implementation. Record the independent
  commissioning channel and who can authorize source/status recovery. Keep secrets
  out of the record; a reachable endpoint is not provenance.
- [ ] Check that every proposed assignment is authorized for its exact scope and
  that any claimed independence satisfies the applicable policy. Global institutions
  are required only for the corresponding global claim; do not downgrade the
  selected Connector profile to fit available signers.

**Exit evidence:** a complete C1-C6 inventory with independently verifiable public
provenance and explicit blocked rows. Names/URLs alone do not pass this gate.
**If blocked:** identify the exact missing source/owner input. Existing fictional
fixture identities must not fill the row, and repeated vectors cannot close it.

### P2 - Resolve only the remaining protocol and source-contract decisions

**Responsible role:** protocol owner approves new contracts; source operators
confirm their acceptance, coverage and delivery obligations.
**Document:** this record; any later normative amendment gets its own explicitly
versioned proposal with pinned parents, never an in-place rewrite of old authority.

- [ ] Specify each source's accepted-update boundary, authenticated cut/epoch
  ordering, commitment construction, complete scoped coverage and cross-domain
  dependency closure. Decide explicitly between verifiable coverage and a bounded
  accepted omission-trust assumption; witnesses are not implicitly completeness
  authorities. Include empty intervals, gaps, forks and source replacement.
- [ ] Bind the dedicated publisher and status roles to authorized commissioning
  evidence. Specify publisher withdrawal and independent status-anchor recovery,
  including wire/schema, replay ordering and retained negative effects; W4 currently
  has only an authorized response and must not gain an invented negative variant.
- [ ] Resolve the still-pending Connector action/profile allocation, accepted inner
  artifact versions and the relationship of W6 limits to existing WP8 timings.
  Assign numerical values only through the applicable reviewed profile decision.

**Exit evidence:** exact reviewed schemas, signer-authority matrix, canonical
transcripts and accept/reject rules sufficient for two independent implementations.
Open alternatives remain blockers, not implementation discretion. If a real source
cannot meet the chosen contract, revise the proposal for review instead of relaxing
verification in code.

### P3 - Replace supplied coverage oracles with authenticated evidence checks

**Existing boundaries to reuse:** `nbsr/federation/trust.py`, `cose.py`,
`delegation.py`, `transparency.py`; the versioned normal-revocation/inclusion
verifiers and the existing currentness/source-coverage fixture suites.
**Implementation deliverable:** a separately scoped offline verifier/composition
patch for the exact P2 contract. Name its new module/test paths in that patch's
implementation scope after P2 fixes the interface; do not turn the present symbolic
checker into a runtime provider by renaming its result.

- [ ] Author literal positive and negative artifacts for all six domains using
  approved public test material. Separate coverage acceptance from admission: a
  complete view containing a denial is not permission to register.
- [ ] Independently verify signatures, signer authorization, exact scope and
  dependencies, source cuts/completeness and publisher status. No injected success
  result may stand in for any claimed cryptographic acceptance path.
- [ ] Test omitted accepted records, cross-domain substitutions, missing governance
  evidence, unauthorized signer/roster changes, empty intervals, same-cut conflicts,
  replay and stale evidence. Verify actual controller/normal/emergency semantics,
  not merely mocked verdict propagation.

**Exit evidence:** reproducible byte/transcript and semantic results plus affected
CI selection. Preserve the earlier 92 symbolic cases as historical model evidence;
new composed positives must identify exactly which real-verification boundary they
exercise. Offline cryptographic success still does not establish deployed provenance.

### P4 - Implement and prove restart and time boundaries

**Reuse candidates:** `scripts/inclusion_persistence.py` and
`tests/federation/test_inclusion_persistence.py`; existing client restart/floor
patterns and the `TimeWindow`/observation invariants in the native authority target.
These are starting points, not an approved complete Connector backend.

- [ ] Select the deployment's independent restart anchor, namespace and authenticated
  first-provisioning/recovery procedure. Specify write-before-publication ordering,
  uncertain-commit behavior and compatibility with software rollback under F55.
- [ ] Implement the bounded persistent adapter; test missing/corrupt state, rollback
  of both local files, interruption at each publication boundary and failed cleanup.
  Preserve denial markers, future events and visible ownership on uncertainty.
- [ ] Select the actual clock/uncertainty source and serialized scheduling boundary;
  test clock rollback, excessive uncertainty, suspend/resume, delayed event delivery
  and expiry during verification. Same-cut refresh cannot extend the deadline.

**Exit evidence:** independently anchored restart rejection and measured timer/
uncertainty behavior for the selected environment. Distinguish injected exceptions,
process crashes and power loss; claim only the durability level actually tested.
M3/M4 remain open if evidence is still a memory backend or supplied clock.

### P5 - Integrate the real provider with the development Connector path

**Existing integration boundaries:**
`crates/nbsr-transport/src/connector_authority.rs`, `connector_cleanup.rs`,
`tests/federation/test_connected_authority_vectors.py` and
`interop/nbsr-go-peer/connector/README.md`. Inspect their current callers before
selecting exact production module ownership; test-only source is not promoted by
removing a build guard or changing registration_ready() alone.

- [ ] Implement the P2 provider interface with the approved bounded transport and
  independently provisioned identities. Consume the P3 verifier and P4 storage/time
  results in one serialized final recheck before ownership/admission changes.
- [ ] Prove that authority revision, scope, key, request/session and deadline changes
  between verification and acceptance reject the stale result. Keep partial-view
  rejection separate from processing independently verified negative events.
- [ ] Exercise real parser/verifier-to-owner integration: termination, expiry,
  network outage, reconnect and cleanup failure. No replacement session before
  confirmed cleanup; wrong/stale cleanup tickets must not release the old owner.

**Exit evidence:** focused integration results and one scoped correctness review;
all applicable source/authorization paths enforced without synthetic success inputs.
Any change to pinned runtime source authority needs its separately reviewed versioned
approval. This plan neither refreshes an old overlay nor authorizes live admission.

### P6 - Separately authorized pilot and Stage 3 acceptance review

**Responsible roles:** deployment owner authorizes the exact disposable pilot;
implementer retains evidence; acceptance reviewer evaluates the existing gate.

- [ ] Before execution, define exact hosts/resources, credential provisioning method,
  scope, limits, abort criteria and cleanup ownership. Verify free-space/build guards
  and existing resources without restarting Docker or modifying unrelated resources.
- [ ] Demonstrate real-source Connector registration and current authority, plus
  each applicable revocation mode, publisher withdrawal, stale/missing domains,
  network recovery, process restart/rollback rejection and failed-cleanup retention.
- [ ] Retain commit/dirty-source/binary identity, approved profiles, public provenance,
  redacted commands/logs, observed results and exact cleanup counters. Keep failed
  attempts and distinguish synthetic regressions from actual-source acceptance.
- [ ] Review every Stage 3 obligation against retained evidence. Missing source
  coverage, uncertain restart/time, unverified governance or unconfirmed cleanup
  prevents closure. Track later-stage operational obligations separately; neither
  local pilot success nor this plan claims global governance or production readiness.

**Exit evidence:** an explicit acceptance decision with unresolved items listed,
not an automatic status transition. No READY, activation, commit, push or merge is
authorized by this plan. The immediate next deliverable is P1's concrete inventory;
P2 can prepare proposals around remaining unknowns but cannot fabricate their answers.


<a id="connector-source-inventory"></a>

### P1 document-derived inventory: evidence and missing assignments - 2026-11-26

This is P1's documentation pass, not commissioning acceptance. Reuse C1-C6 for
contracts, the WP8 reconciliation for governing decisions and T1-G3 for verifier
ownership; none of those tables is duplicated or replaced here. The rows below
add only the classification of available source evidence and absent deployment
assignments. "Not established" means not established by the checked documents,
not proof that no such service exists outside this checkout. No endpoint was
contacted, reference resolved or credential store opened.

| Domain | Available evidence / classification | Deployment assignment still not established |
| --- | --- | --- |
| C1 | T1 and historical F47-F49 identify the trust package and scoped authority model. The [config README](../../deploy/single-instance/README.md) explicitly classifies repeated-byte identities and ref:* names as illustrative; no provider or secret-store binding is selected. **Documented contract; no commissioned source evidence.** | Actual scoped trust authority/root custodian, authenticated initial bundle and independent commissioning channel; accepted public key/lineage, log/witness roster and source endpoint. An inventory of authority classes in a registry is not an inventory of deployed authorities. |
| C2 | T2-T4 identify key/ownership/delegation inputs. The [native genesis review](2026-11-14-native-signed-genesis-evidence.md) verifies a bounded retained corpus using supplied test signers, not a runtime authority. **Signed fixture evidence only.** | Real operator, Connector peer key, owner/delegator and exact service/Gateway binding; authenticated live chain/status source and current coverage. gateway.fixture and gateway.example.test in the example are not selected deployment values. |
| C3 | The [Development Profile signer matrix](../protocol/federation-v0.1-development-profile.md#signer-authority-matrix-and-cose-kid-binding) identifies target-controller authority. The [Connector README](../../interop/nbsr-go-peer/connector/README.md) labels authority/revocation receipts synthetic. **Authority rule and synthetic integration; no real controller assignment.** | Exact controller identity/key and authorized target scope; authenticated controller revocation source, acceptance history/cut and recovery operator. Transport success in the harness supplies none of these. |
| C4 | The [normal conformance registry](../protocol/registries/federation-v0.1-normal-revocation-conformance-v1.json) names normal-revocation-v1 and the normal-revocation group, with runtime_enabled=false and live_enabled=false. Its [review](2026-10-11-normal-revocation-conformance.md) labels membership/control domains as supplied fixtures. **Explicit local conformance policy, not deployed roster.** | Actual five-member eligible roster, independently authenticated control-domain evidence, governing configuration, live normal-record source and applicable log/witness sources. No global-trust-v1 substitution. |
| C5 | The same Development Profile defines the emergency authority alternative; C5 and the Connector gate retain its bounded deny-only semantics. No commissioned emergency roster/feed is established by the inspected profile, registry and Connector evidence. **Documented authority rule; deployment unverified.** | Actual eligible emergency members, purpose-bound keys, authorized source/cut, operational notification and recovery assignments. The normal group or local test signers cannot silently fill this row. |
| C6 | W4/W5 define the proposed dedicated publisher/status roles. W8 and the six-domain fixture section explicitly describe supplied trust and symbolic source cuts. **Draft role/receipt contract and offline fixtures.** | Named publisher and independently administered status authority, authenticated grant/status anchor, eligibility ledger, concrete transport identities and withdrawal/recovery authority. No existing WP8 purpose or reconciliation-controller role automatically authorizes these new signatures. |

**Shared unresolved deployment bindings:** the checked record does not establish
an actual selected pilot scope/profile, public fingerprint inventory, authenticated
source-ID-to-endpoint mapping or accepted source-contract versions for these six
rows. Existing approved development contracts remain the baseline; selecting an
operational scope cannot weaken their obligations. The three logical config
references remain placeholders until independently provisioned and authenticated:
`trust_ref`, `registration_policy_ref` and `registration_authority_ref`. Do not
replace them with examples or infer their contents from their names.

**Minimum next input, without secrets:** the deployment owner supplies the intended
scope and accountable role assignments; each selected authority/source owner
supplies public identity/key fingerprints, authorized scope, endpoint identity,
lineage/provenance and an authenticated sample cut/history. The independent
commissioning/recovery custodian supplies the provenance channel and recovery
assignment. Record each item against C1-C6 here only when evidenced. A source not
yet available becomes a specifically scoped implementation requirement, not a
fictional populated row. Whether a missing source is absent or merely undocumented
requires owner confirmation or separately authorized inspection.

**P1 result:** documentation inventory prepared; commissioning gate remains open.
No concrete real-source row can be marked authenticated from this evidence alone.
The remaining proof-format/coverage and publisher-status decisions stay in P2;
M3/M4 and runtime integration stay in P4/P5 rather than being relabelled as missing
WP8 architecture. No existing section required a substantive correction in this
pass; all prior text is retained byte-for-byte.


### P2 draft: real-provider boundary behind ACP/enrollment - 2026-11-26

This specifies responsibilities for a future implementation, not a deployed
provider or a new wire allocation. Reuse the WP8 mapping, C1-C6 source contracts,
W3-W6 draft and P1 inventory above without duplicating them. Actual authorities,
keys, endpoints and independent provisioning remain unverified P1 inputs.

**Composition:** independently authenticated commissioning -> verified WP8 source
records and coverage -> immutable scoped authority snapshot -> policy/credential
services -> existing ACP/enrollment adapters. A separate Connector adapter may
consume the shared verified snapshot only after its registration/profile mapping
is approved. It must not interpret a client ACP result as Connector admission.
The publisher transports/attests the declared view; the Gateway independently
verifies it. Neither the enrollment service nor the reconciliation controller
may manufacture governing authority missing from that view.

#### Existing interfaces and required real implementations

The interfaces in [source_operator_runtime.go](../../client/nbsr-go-client/internal/authority/source_operator_runtime.go)
are injection boundaries, not evidence that their real implementations exist.

| Existing boundary | Required real source and behavior | Connector reuse limit |
| --- | --- | --- |
| ACPRequestKeyResolver / RequestKeys | Resolve the exact device/kid/generation from an authenticated enrollment/credential registry, with validity, status, purpose and operator binding. Unknown or ambiguous identity rejects. Registry writes require the authorized enrollment/recovery path. | Reuse exact-key validation patterns; a client device credential does not become a Connector purpose-14 KAR or establish C2 ownership/delegation. |
| OperatorResultSigner | Obtain the dedicated purpose-bound signer from the deployment's approved key-custody service, authorized by the accepted scoped chain. Check its current eligibility before signing; do not generate replacement keys as a request fallback. | Existing ACP/enrollment purposes 15/16 remain limited to their existing results. W5 publisher/status keys and governing record keys need their own approved authorization; no purpose reuse by analogy. |
| SourceOperatorAuthority.CurrentAuthorityGeneration / DecideAuthority | Read a committed, internally consistent scoped snapshot and independently authorized local policy. Evaluate the exact verified request against governing evidence, dependencies, denials, time and policy; policy may narrow but cannot create authority. Return only existing ACP artifact/status types with the generation actually used for evaluation. | Reuse the decision boundary, not the client result schema. The Connector needs its separately approved inventory/session/request/peer binding and owner lifecycle. |
| BootstrapAuthorizer | Authenticate initial provisioning through the deployment-specific channel and resolve a scoped enrollment entitlement from a durable ledger. Bind the authenticated subject, intended operator/profile and allowed enrollment operation; never derive entitlement from an unverified request field. | Reuse the separation of bootstrap authentication from wire parsing; it does not itself issue service delegation or authorize Connector registration. |
| InitialEnrollmentService | In one serialized decision, bind the authenticated subject to the verified device request, validate the initial-only entitlement and commit the credential outcome. Existing-subject replacement is rejected under the current interface; recovery is a separately authorized operation. | Reuse request/result binding and initial enrollment transaction rules. Connector trust provisioning and registration remain distinct. |
| IssuerResolver / EnrollmentResultIssuerResolver / ACPResultIssuerResolver | Supply validated issuer records from the commissioned root/policy lineage and current status, retaining exact purpose, scope, key and validity constraints. StaticIssuerResolver can hold an already authenticated snapshot; constructing it does not authenticate that snapshot's origin. | Reuse signer resolution checks; full Connector governing closure, threshold packaging and source completeness remain mandatory. |
| CheckpointEvidenceVerifier | Verify the approved inner evidence bytes and their authority/currentness, independently of the outer ACP result signature. Reject injected success labels, missing domains, stale cuts and inconsistent dependencies. Produce claims only for the exact request/operator/profile and verified snapshot. | The existing client CheckpointClaims is not a six-domain Connector proof. A versioned mapping/adapter is needed; W3 evidence must not be silently serialized into existing opaque bytes and treated as approved semantics. |
| GenerationFloorStore / EnrollmentStateStore | Implement the existing pristine-versus-lost-state distinction, durable publication and authenticated recovery contract. Preserve committed identities, retained denials and scope-specific safety state; uncertain writes fail closed. | Client enrollment storage or idempotency persistence does not supply all Connector C1-C6 floors. Reuse M3 invariants; define the exact Connector namespace and independent anchor before use. |
| NowUnix / Clock | Supply the selected deployment clock and enforce the approved uncertainty/monotonic policy at decision and publication boundaries. A default wall-clock callback is not proof of W6 uncertainty bounds. | Apply M4; do not substitute ACP wall time for the Connector's bounded authority window. |

#### Snapshot acquisition and publication contract

1. Load the independently provisioned trust context and exact C1-C6 source contracts.
   Resolve only explicitly authorized sources. Network identity is transport evidence,
   not permission to trust new roots, roster members or status signers.
2. Ingest original authenticated records and required proofs; perform resource,
   canonical encoding, signature, purpose, scope, lineage, typed governance and
   source-coverage checks. Reuse existing verifiers under their approved versions;
   no generic single-signature fallback for threshold evidence.
3. Construct a candidate immutable view with all relevant dependency bindings,
   cut vector, retained denials and future events. P2's not-yet-approved coverage
   proof/omission-trust decision remains required; an unimplemented check cannot
   be replaced by a locally incremented revision or an empty result.
4. Under serialized commit control, recheck the governing context, status, clock
   and current floors. Persist the candidate safety state using M3 before publishing
   it for decisions. A failed/uncertain commit cannot publish fresh authority or
   release ownership. Verified negative effects follow their approved typed path
   even when a complete positive view is unavailable.
5. Return a decision tied to the exact installed snapshot, with a final revision
   and expiry check before result publication or Connector ownership transition.
   Source succession, policy change or revocation invalidates affected pending work;
   it cannot renew expired authority or clear retained withdrawal markers.

The scalar client AuthorityGeneration must identify a committed client-authority
view under its existing rules. It is not a comparison rule for unrelated C1-C6
counters. Define an explicit, reviewed snapshot-to-client-generation binding if
this shared provider serves ACP, while retaining the full Connector cut vector.
Never derive the generation from HTTP success, wall time or publication attempts.
No concrete mapping or new serialization is allocated by this draft.

#### Enrollment atomicity and authorization boundary

[EnrollmentHTTPClientConfig](../../client/nbsr-go-client/internal/authority/enrollment_client.go)
explicitly leaves deployment bootstrap authorization outside generic enrollment
wire serialization. Select and review the authenticated provisioning channel;
do not add an ad hoc token/header or weaken TLS to make a demo enrollment work.
BootstrapAuthorization currently exposes only Subject, so the service must resolve
scope/expiry/consumption in its trusted ledger, or propose an interface amendment
if that cannot safely express the approved entitlement. Subject text alone is not
an enrollment grant.

Consuming the entitlement, assigning the initial credential and retaining its
terminal request/result binding must have a documented atomic recovery boundary.
Coordinate that boundary with the runtime's transactional idempotency store: a
crash after entitlement consumption cannot mint a second credential or silently
repeat initialization. Exact retries recover the committed outcome; conflicting
requests reject. Uncertain outcomes remain blocked until reconciled, never repaired
by dropping ledger entries. Backend choice and cross-store transaction strategy
are implementation decisions still to specify, not guarantees of the current API.

#### Focused acceptance requirements and remaining decisions

Before claiming a real-provider implementation, demonstrate: unprovisioned/ambiguous
key rejection; valid signature with wrong purpose rejection; unauthorized local
policy expansion rejection; expired or replayed bootstrap rejection; conflicting
initial enrollment and post-consumption crash recovery; outer-valid/inner-invalid
freshness rejection; all C1-C6 missing/stale/conflicting coverage negatives; source
revision or revocation change during evaluation; uncertain durable publication;
clock rollback/uncertainty failure; and cleanup failure retaining the exact owner.
These are required future tests, not results obtained by this documentation change.

Existing transport, codec, key-resolution, idempotency and restart checks are reuse
candidates. Still missing are the real source assignments, approved completeness
proof, dedicated publisher/status authorization and withdrawal format, any needed
client-generation/Connector mapping, provisioning transaction backend and M3/M4
runtime evidence. Keep these as P1-P5 gates; do not invent a second set of contracts
or change approved WP8 semantics. This draft authorizes no activation, READY,
commit, push or Stage 3 closure.


#### Offline provider seam vectors - 2026-11-26

The approved provider direction now has a separate bounded
[literal fixture package](../../vectors/acp-provider-contract-draft1/vectors.json),
[checker](../../scripts/verify_acp_provider_contract_vectors.py) and
[tests](../../tests/protocol/test_acp_provider_contract_vectors.py). These add only
proposed provider transaction/publication seams. Existing Go enrollment signature,
request binding and runtime idempotency tests remain in their current files; the
currentness and six-domain coverage packages remain unchanged. No second copy of
those protocols or verifiers is introduced. Expected outcomes/final states were
authored independently of the checker; no generator calls it to choose expectations.

The 28 literal traces contain 6 positives and 22 negatives. Positive traces cover
initial reservation/commit, exact pending/committed retries, authenticated matching
reconciliation after an uncertain commit, recovered replay and valid publication.
Negatives cover denied entitlement, subject/request conflicts, uncertainty blocking,
wrong/unverified reconciliation, commit without reservation, uncertain completion,
credential replacement, unknown operations, failed supplied verification/storage/
clock/signer/policy checks, changed revision/digest/policy, expiry equality and
attempted conversion of a client ACP result into Connector registration, and
publication while enrollment is pending or uncertain.

The checker is a symbolic offline model. subject-a, request-a, credential-a and
snapshot digests are opaque fixture labels, not serialized identities, keys or
hash proofs. Authorization, storage confirmation, clock validity, policy narrowing
and inner verification are injected oracle verdicts, never authenticated provider
outputs. The model reserves one credential label and never resets uncertainty to
pristine; matching authenticated committed evidence is its only reconciliation
success. It does not specify a real storage recovery algorithm. Positive pending
and replay traces mean expected bookkeeping, not new authority or admission.
OFFLINE_PUBLICATION_VALID is likewise a fixture result, never READY.

Standalone publication cases assume an already authenticated actor; pristine
means no transaction in this trace, not permission for an unenrolled device.
The model does not execute cryptography, real entitlement expiry/consumption,
cross-store transactions, crashes, revocation delivery, clock uncertainty estimation,
C1-C6 verification or the concurrent Gateway lifecycle. Those P2-P5 obligations
remain open; existing Go tests are referenced as coverage ownership, not rerun or
claimed as new evidence here. No sockets, Docker, key generation or filesystem
credential/ACL operations are required by this package.

Focused commands from the isolated root:
```text
python -B -m scripts.verify_acp_provider_contract_vectors --check
python -B -m pytest -q -p no:cacheprovider tests/protocol/test_acp_provider_contract_vectors.py tests/protocol/test_connector_currentness_vectors.py tests/protocol/test_connector_source_coverage_vectors.py tests/ci/test_ci.py -k "not connector_docker_supervisor"
```
CI's python-protocol profile selects the checker and the tests through its existing
tests/protocol collection. Literal traces pin intermediate results and final state;
unit checks also reject truthy non-booleans and preserve consumed ownership during
failed reconciliation. Hosted execution and real-provider acceptance are not implied.


### Pilot selection and remaining trust choices - 2026-11-26

**User-selected direction:** a pilot with external operators/partners that have
existing authorities. **Assignment status:** the user has not identified any
partner or authority. This is a target topology, not evidence that a suitable
provider exists, participates in NBSR or has agreed to a pilot. No partner outreach,
endpoint connection or activation is authorized. Keep P1's six-domain inventory;
fill evidenced assignments there rather than creating a second inventory.

#### D1 - Qualify a partner before choosing a product or endpoint

Recommend a bounded first pilot with one service, one Connector and one Gateway,
while preserving all applicable governing authority modes and independence rules.
The number of transport participants does not set the number of governing signers.
Do not infer independent authorities from multiple containers, keys or accounts
under one administrative control.

A candidate partner must supply public documentation or an independently
verifiable statement identifying its operator identity, authority scope, key
provenance/rotation, governing roster/control domains, signed record/proof formats,
revocation distribution and coverage semantics, clock/availability commitments,
and accountable commissioning/recovery contacts. Check those against C1-C6 and
the approved WP8 mapping, recording supported, adapter-needed and unsupported
requirements. A CA certificate, OIDC issuer, generic signing service, ISP status
or HTTPS API does not by itself qualify as an NBSR governing authority.

If a candidate offers a compatible authenticated source, specify a narrow adapter
that preserves original signed records and all authority checks. If it only offers
key custody, identity bootstrap or infrastructure, classify that limited role;
do not relabel it as a complete authority provider. If no candidate can supply the
required authority and evidence, the external-pilot gate stays blocked. Offline
implementation can continue only under explicit fixture boundaries, without
substituting the previously unselected private deployment profile.

#### D2 - Recommended coverage choice: source-authenticated cuts

For the external pilot, recommend independently authenticated per-domain source
cuts and coverage attestations over the exact accepted history/scope. The
publisher assembles and transports them; its own signature alone is insufficient
for a new positive acceptance. Reuse W3's required_evidence_refs and existing
artifact verification where applicable; do not silently invent an object type or
purpose for a source attestation. P2 must specify and approve the exact encoding,
signing authority, commitment and verification rules before implementation claims.

This chooses stronger separation than trusting the publisher alone, but is not a
cryptographic proof that an authoritative source never withheld an update. Each
source's acceptance boundary, honesty/completeness assumption and independent
observation/audit must be documented. Inclusion and consistency still do not prove
absence of omissions. Unknown coverage, missing domains or mutually inconsistent
cuts block a fresh positive view under existing W3/W6 rules.

**Alternative not selected:** publisher-only completeness under an explicitly
accepted omission-trust assumption. If a future partner cannot supply the
recommended source evidence, return for that specific trust decision; do not
fall back automatically or claim that a fresh signature closes the gap.

#### D3 - Recommended publisher/status authorization choice

Reuse W5's distinct publisher and status keys. The independently authenticated
commissioning package authorizes the scoped PublisherGrant and pins the status
anchor; the status service maintains an independently administered grant/key
eligibility ledger. Actual organizations, keys and custody remain P1 assignments.
Separate key IDs alone do not prove administrative independence, and the status
service never replaces controller/normal/emergency governance.

Require a request/view-bound authorized status receipt for each fresh acceptance.
Choose a separately authenticated withdrawal path with retained negative markers,
and recovery through the independently authorized commissioning successor process.
A later authorized receipt cannot erase a withdrawal by itself. Exact withdrawal
schema, signer authorization, ordering and recovery transitions remain P2 decisions;
this recommendation does not add a negative variant to W4's existing draft.

#### Next deliverables and approval boundary

1. Identify candidate partners and obtain public capability/provenance information;
   populate only evidenced P1 assignments. No names are invented in this record.
2. Review D2/D3 as the recommended trust choices. Their acceptance is separate
   from the already selected external-pilot direction and does not approve a wire
   format, endpoint, credential or live run.
3. Once candidate capabilities and the trust choices are settled, produce the
   exact P2 proof/withdrawal contracts and compatibility mapping, then implement
   the P3-P5 boundaries already planned. Do not repeat earlier lifecycle/vector
   work without new integration risk or evidence of a defect.

No current vendor, partner availability or external authority compatibility was
researched or verified in this step. No activation, READY, commit, push or merge
follows. The concrete external-pilot blocker is now explicit: no identified
partner with authenticated C1-C6 capabilities, rather than missing WP8 principles.


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

Maintain C1–C6 assignments and their accepted evidence only in the existing
[P1 source inventory](#connector-source-inventory). The table below tracks the
supporting roles and mechanisms; its C1–C6 row is a cross-reference, not another
assignment/status register. When a source is accepted, append its versioned
evidence there without erasing the original unassigned assessment.

| Record | Existing contract to satisfy | Accountable real source / custodian | Qualifying evidence reference | Current state |
| --- | --- | --- | --- | --- |
| Commissioning and recovery | M1, W5, S1/S4: independent package authentication and authorized succession | UNSELECTED | UNVERIFIED | Blocks trust import |
| C1–C6 | Existing domain contracts and [P1 source inventory](#connector-source-inventory) | Maintained in P1 | Maintained in P1 | See the single source inventory |
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


## Consolidated checkout and retained lifecycle evidence — 2026-11-28

This is source/evidence reconciliation, not a new live trial or Stage 3 closure.
The continuation branch is `codex/nbsr-v3-wp0-wp1`, starting at
`e82a2fc036bad41ebddf3d2203243edf8075ae5b`. The separate clean checkout preserves
the dirty original checkout. Published P1, Docker harness and offline integration
are already in that ancestry. The older admin/JSON branches add no missing runtime.
Existing unpublished ACP provider-contract and Option C offline additions were
copied from the preserved `publish-currentness` checkout, without changing their
code/test/vector bytes; prior document additions and current signing/P1 guidance
are retained. These are existing offline fixtures, not a new provider implementation.

The [reconciliation receipt](2026-11-28-connector-evidence-reconciliation.json)
records exact external evidence locations, receipt/log digests, binary hashes,
source-snapshot checks and differences from the current base. Original artifacts,
including unsuccessful attempts, remain in their operator-owned evidence directory.

| Retained Docker case | Result | Cleanup-inclusive duration | Source identity |
| --- | --- | --- | --- |
| SIGTERM and process restart | PASS | 3.99 s | `71063cdd` plus `docker-attempt-7/source` |
| SIGKILL and process restart | PASS | 9.44 s | Same base plus `sigkill-attempt-1/source` |
| Network loss/restoration and supervised replacement | PASS | 11.20 s | Same base plus `network-attempt-1/source` |
| Automatic reconnect in the same process | PASS | 10.67 s | Same base plus `auto-network-attempt-1/source` |
| Five network cycles, six accepted sessions | PASS | 40.90 s | Same base plus `five-cycle-attempt-1/source` |
| Injected cleanup failure and explicit retry | PASS | 14.72 s | Same base plus `cleanup-failure-attempt-1/source` |

Full historical base: `71063cdd50b27ebbbcd57ce011f20f6743b815a0`.
All 99 recorded source-snapshot hashes and all 12 binary entries were checked
against retained bytes. Each receipt reports no cleanup errors and equal before/
after resource inventories. Redacted logs remain available. Earlier Docker attempts
1–5 failed; attempt 6 passed before the final address-policy refinement; attempt 7
is the retained final graceful result. Their failures were not removed or relabelled.

These were dirty-source trials, not clean-SHA runs. In the latest cleanup-failure
snapshot, all 17 recorded source files match the current base after CRLF comparison
except `docker_trial.py`; earlier snapshots differ in additional harness files.
Neither this subset comparison nor retained PASS certifies the current build.
The later supervisor hardening has eight passing local unit tests here, not a new
live Docker receipt. Existing loopback regression log `loopback-final.log` reports
one aggregate test passed; its report describes the internal 19-case matrix.

### What remains for a separately authorized VM verification

First select one immutable consolidated source and retain its build/fixture hashes.
The Docker supervisor uses Docker-specific process/network observations and private
fixture IPC; it is not a drop-in VM launcher. Review an existing VM runner's exact
support before reusing it, rather than claiming the Docker cases already ran there.
Then verify the supported registration/renewal, restart/kill, network/reconnect and
cleanup-retention cases on two endpoints, retaining raw redacted logs, process
identity, generation changes, socket release and exact cleanup ownership. A prior
reported SPHERE registration/renewal success is not substituted for those logs or
for this current-source matrix. No VM execution or adaptation is authorized here.

Real C1–C6 authority, trusted currentness/time, independent durable rollback state
and private-service dispatch through accepted registration remain separate gates.
The six Docker receipts explicitly use synthetic authority and do not establish
READY. VM success under the same fixtures would not close those gates.

Consolidation checks: 69 focused pytest cases, eight supervisor unit tests, retained
ACP vectors (6 positive / 22 negative), Option C fixture validation and scoped Ruff
passed. The initial broader selection failed on sparse-missing fixtures/workflows
(52 failed, 73 passed, one deselected); after targeted materialization the focused
selection above passed. The broader CI suite was not rerun. CI command inspection
confirms the existing python-protocol profile collects the imported protocol and
federation tests and selects the ACP checker. No new Go/Rust build, live Docker
trial, VM access, performance run or hosted CI execution occurred.
