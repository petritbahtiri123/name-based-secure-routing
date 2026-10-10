# Outbound connector control profile — stage 1 review draft

**Status: PROPOSED protocol; approved mock-only slice implemented, runtime NOT implemented.** This document defines a
review boundary, not a wire standard, new trust root or authority overlay. It
does not allocate message IDs, ALPN values, signer-purpose identifiers,
credentials, numeric lease limits or deployment permissions. Existing frozen
contracts win over this draft. No runtime behavior changes accompany it.

Scope: one origin-side connector, one explicitly authorized Service Identity,
one destination gateway and at most one accepted live registration. No origin
traffic in the first control harness; relay follows roadmap stage 5. A reachable
gateway is required, but its public/private placement is not selected here.

## Sources and authority classification

Inherited requirements, verified against current repository sources:

- `docs/architecture/NBSR_Protocol_Vision_V3.6.md`, identity distinctions and
  end-to-end flow: endpoint/connector reachability is not Service Identity;
  destination admission is independent; origin details stay hidden from clients.
- `originset-compatibility-authority-decision.md`, D7-2: owner or explicitly
  delegated authority, service/scope/time/generation/revocation binding, and
  caller-supplied operator/federation trust context. Authenticated transport
  does not itself authorize publication. These are authority constraints, not
  an existing connector-registration wire protocol.
- `nbsr/protocol/states.py`, ConnectorState and _CONNECTOR_TRANSITIONS: the
  only currently allowed edges are the normal sequence shown below.
- `docs/architecture/NBSR_Protocol_Vision_V3_and_Codex_Build_Directive.md`,
  section 11.4, and the recovered original direction linked in the roadmap:
  the connector initiates outbound from the private-service network.

The ten-stage roadmap at
`docs/superpowers/plans/2026-10-10-single-instance-operator-package.md` supplies
the bounded scope, no ambiguous application replay, resource ownership and local
demo/pilot separation. The following registration, lease and recovery mechanics
are **recommendations for approval**, not claims that the inherited documents
already specify them. Existing transport primitives are reusable; source/device
credentials and RouteGrants are not implicit connector-publication authority.

## Proposed identity and registration binding

Use explicit provider interfaces for trust, time, proof verification and
revocation. Resolve all identities inside a configured trust context; never
treat an untrusted key identifier as a global lookup or network address.

The verifier's logical input must bind the following concepts. Names below are
review vocabulary, not serialized field names or approved signature transcripts:

| Binding | Proposed rule |
| --- | --- |
| Connector principal and proof | Authenticated peer proves possession of the explicitly authorized connector key; a display name or TLS success alone is insufficient. |
| Service | Exact Service Identity and applicable ServiceRecord generation; no wildcard, origin-address-derived identity or cross-service registration. |
| Delegation | Owner/approved authority chain explicitly permits this connector's registration/reachability role, scope and validity. Registration permission is not assumed to include OriginSet publication permission. |
| Destination | Exact authorized gateway identity and consuming operator/trust context; endpoint address is only a locator. Both peers authenticate the intended counterparty. |
| Freshness | Validity, generation, sequence where applicable and current revocation inputs are checked before acceptance and renewal. |
| Connection instance | Acceptance is bound to the authenticated live connection and a fresh attempt correlation value; a prior connection's acceptance cannot be replayed. Encoding and proof binding require review. |
| Local target | An origin-side configured service mapping only. It cannot expand delegation or appear in client-facing health/errors. |

Recommended acceptance is conjunctive: authenticated peers AND exact service
delegation AND current freshness/revocation AND correct gateway/operator AND
available bounded resources. Failure of any check produces no live registration,
no READY and no origin access. Gateway registration selection is followed by
independent destination admission for every later authorized service flow.
There is no new authority issuer, automatic enrollment or fallback key provider.

## States, registration and failure handling

The inherited legal normal path is exactly:

`DISCONNECTED -> CONNECTING_OUTBOUND -> AUTHENTICATED -> READY -> DRAINING -> DISCONNECTED`

| State | Proposed operational meaning |
| --- | --- |
| DISCONNECTED | No accepted live registration or owned connection; a bounded policy may schedule a new attempt. |
| CONNECTING_OUTBOUND | Own one outbound attempt; not eligible for dispatch. |
| AUTHENTICATED | Peer authentication complete, service registration still unaccepted; not eligible for dispatch. |
| READY | Gateway has atomically accepted the connection-bound service registration and local confirmation is valid; eligibility still requires unexpired, unrevoked authority and live connection. |
| DRAINING | Registration is ineligible for new work; existing work follows the approved graceful/forced cleanup policy. |

Gateway dispatch-table presence and local readiness are separate observations.
Recommended gateway commit point: after all checks, atomically install the one
registration, then send its bounded acceptance. Connector reports READY only
after validating that response on the same connection. If confirmation is lost,
no user work is allowed by the control-only harness; the gateway record remains
subject to connection loss/lease expiry and cleanup. Later dispatch must tolerate
this distributed-state interval without bypassing per-flow authorization.

**Unresolved state-model gap:** current code has no failure edge from
CONNECTING_OUTBOUND or AUTHENTICATED, including handshake failure, rejection or
stop. Do not synthesize AUTHENTICATED/READY to reach DRAINING, directly assign an
illegal transition, or change the frozen map silently. Recommended first work is
a pure attempt-owner model: rejected attempts release resources and report a
terminal outcome separately from successful lifecycle states. Whether this
separation satisfies the governing lifecycle or needs explicit versioned failure
edges must be approved before integrating an automatic retrying runtime.

For failures from READY, use the allowed DRAINING path while immediately making
registration ineligible. Cleanup completion precedes DISCONNECTED and any next
attempt. Forced revocation must not be treated as permission for graceful
application drain when authenticated enforcement requires terminate-active-use.
The former blanket immediate-cancel recommendation is superseded by the
mode-aware reconciliation below; deny-new-use does not itself terminate active work.
Graceful operator stop may drain only still-authorized work within an approved
deadline. These policies and their exact state representation require approval.

## Proposed lease, reconnect and revocation semantics

- A lease grants bounded registration eligibility, not service authority. Its
  deadline must not outlive any governing delegation/freshness deadline.
  Renewal rechecks all authorization and ownership conditions; no heartbeat or
  transport activity extends authority by itself. Reject late/stale renewal.
- Gateway enforces eligibility locally without relying on connector cooperation.
  Connector also withdraws readiness at its local authority/lease boundary.
  Absolute authority time versus monotonic scheduling, allowed clock uncertainty,
  and behavior on clock discontinuity need an approved policy. Unverifiable
  freshness cannot create or extend a registration.
- On observed disconnect, withdraw eligibility before scheduling retry. Silent
  peer failure is bounded by approved liveness/lease deadlines, not assumed to
  be detected instantly. Close/reap the old owner before a new local attempt.
- Recommend rejecting a second live registration rather than silently replacing
  one. A partitioned old record therefore blocks reconnect until explicit safe
  removal or expiry; this is a deliberate availability tradeoff. Replacement or
  takeover would need another reviewed fencing protocol and is outside scope.
- Each reconnect authenticates and obtains new acceptance; never persist/reuse a
  live registration, lease, channel, credit or application request across restart.
  Durable authority floors remain governed by existing authority contracts.
- Expiry/revocation makes registration ineligible before new dispatch. Cancel
  active work only when its authority expires or applicable authenticated
  enforcement requires termination; deny-new-use follows the reconciliation below.
  Termination must release owned quota and reap work even if the peer stalls.
  Revocation information delivery and its maximum
  permitted staleness must be selected; this draft promises no instantaneous
  detection of an event not yet received.
- Temporary transport failure may use capped backoff and a finite attempt/time
  budget. Permanent identity/service/delegation rejection halts retries until
  explicitly corrected. Error classification, jitter and budget values are open.
  No automatic failover to another gateway, identity, service or trust context.

Required limit decisions: connect/auth/registration/renewal deadlines; lease and
renewal margin; liveness detection; allowed authority staleness/clock uncertainty;
retry count/total time/backoff; frame bytes, queued controls and stream/credit
budget; graceful drain and forced cleanup deadlines. All must be finite and
internally consistent. No numeric values are approved here; test configurations
must label chosen values as test inputs, not protocol constants.

## Acceptance matrix (runtime acceptance planned; mock coverage recorded below)

Each row needs deterministic expected state, eligibility, side-effect counts and
ownership counters; retain failures as well as passes. Model tests use injected
clock/transport/verifiers; authenticated loopback follows only after the wire and
state decisions are approved. These case IDs are test labels, not wire IDs.

| Case | Input/action | Required observation |
| --- | --- | --- |
| C01 | Valid scoped peers/delegation, two control exchanges | One accepted connection reused; READY only after valid acceptance; zero origin I/O. |
| C02 | Wrong gateway/operator, connector proof or untrusted issuer | Reject; no registration/READY; all attempt resources released. |
| C03 | Wrong service, generation, role or delegation scope | Reject even with valid TLS; no publication/admission authority gained. |
| C04 | Expired/revoked authority, unknown required freshness | No new acceptance or extension; boundary tested just before/at/after expiry. |
| C05 | Old acceptance/renewal replay on a new connection | Reject correlation/generation mismatch; no stale owner revived. |
| C06 | Concurrent/duplicate registration and late old cleanup | At most one eligible owner; rejected/old owner cannot remove another accepted owner. |
| C07 | Lost acceptance, withheld heartbeat or renewal | No indefinite registration; local readiness and gateway eligibility expire under approved clocks/bounds. |
| C08 | Disconnect and reconnect | Eligibility removed on observed loss; capped retries; fresh authorization; no old work replay. |
| C09 | Revocation idle, connecting, registering or credit-blocked | No new affected work; distinguish deny-new from termination. Termination has bounded cleanup; deny-new preserves only still-authorized existing work. Failure-state mapping must be approved first. |
| C10 | Stop/cancel at every await boundary | No fabricated success states; bounded release; legal approved lifecycle/attempt outcome. |
| C11 | Queue/frame/stream budget exhaustion | Bounded rejection; no growing queue, quota leak or peer-controlled indefinite wait. |
| C12 | Auth rejection versus transient failure | Permanent rejection stops retry; transient path stops at finite budget; fake clock proves timing. |
| C13 | Gateway restart or stale durable inputs | No live registration restored; fresh acceptance required; authority floor never lowered. |
| C14 | Expiry/revocation races with renewal or selection | Atomic eligibility check prevents new work once invalidation is applied; cleanup targets exact owner. |
| C15 | Clock jump and revocation-source outage | Approved freshness/outage policy; no accidental lease extension, unconditional authority or automatic classification of outage as compromise. |
| C16 | Logs/health and invalid preflight | No secrets/origin disclosure; preflight performs zero network/write/provisioning; config-valid is not READY. |

Later relay acceptance must additionally prove that a valid connector registration
cannot bypass a wrong/revoked RouteGrant, and that disconnect after origin receipt
does not duplicate the request. The control-only harness can assert the absence
of a data path; it cannot establish those later end-to-end properties.

## Decisions required and smallest safe implementation boundary

1. Approve the exact connector issuer/purpose/delegation and gateway/operator
   trust binding, including separation of registration and publication rights.
2. Approve attempt-failure/cancellation representation against the frozen state
   map; recommend separate attempt ownership first, no implicit new edges.
3. Approve control encoding, connection-bound proof/correlation and stream roles;
   choose a compatible narrow Go/Rust seam without copying crypto. No existing
   source-session API is presumed to implement reverse service registration.
4. Approve lease/clock/revocation freshness, finite limits and fail-closed
   retry classification; recommend one-owner rejection, no takeover protocol.
5. Approve atomic acceptance/eligibility and cancellation/drain rules before
   attaching any application data path.

Recommended next implementation after scoped design approval: a pure one-attempt
registration/ownership model with injected verifier, clock and fake transport;
cover C02–C06, C10–C12 and C14 first. It exercises decisions without keys, network,
new wire constants or pinned transport changes. Mark mocked authorization as
model evidence only. Then add an explicitly authorized loopback control harness
for C01 and actual authentication/revocation cases once the approved wire profile
exists. No customer origin access, provisioning, permanent daemon or expanded
trust belongs to this first boundary. Stage 1 remains review-pending.

## Review and validation record

Design-only consistency review: source authority is distinguished from proposed
mechanics; failure edges are not invented; time/freshness and duplicate ownership
are explicit approval gates; revocation cannot use graceful drain to retain
permission; destination admission and origin privacy remain independent.
No runtime tests, builds, network operations, credentials, authority registry
changes or deployment occurred. Root guidance remains applicable unchanged.
The optional `.agents/skills` directory was absent; no nested docs/protocol
AGENTS.md was found during the bounded instruction check.

### Approved mock-only follow-up

The user approved the simulated slice and retrying its execution. That approval
does not approve this wire profile or activate persistent trust. The isolated
`nbsr/connector_control_model.py` and `tests/test_connector_control_model.py`
now implement a synchronous in-memory owner with injected fake verifier, clock
and transport. No runtime imports were added, frozen states/authority are unchanged,
and there is no I/O, key handling, persistence, automatic timer or background task.

Model choices: one slot/no queue; explicit finite test-input lease/retry values;
single event ordering instead of thread synchronization; exact Python object
ownership instead of wire proofs; renewal atomically returns a new bounded ticket;
permanent verifier failure and backward/invalid time latch closed. Callers advance
time and invoke poll explicitly. Failed close retains a terminal owned resource
and blocks new attempts until explicit cleanup succeeds; failure remains latched.
Attempt phases are deliberately separate from frozen ConnectorState. These choices
are model assumptions, not newly ratified protocol, clock or error-policy rules.

Coverage against C01–C16 is partial: C01 uses model operations, not real control
exchanges; C02–C05 verify simulated bindings/expiry/correlation, not cryptography;
C06 uses sequential duplicate events, not concurrent threads; C07–C10 cover
poll-driven expiry/reconnect/cancel, not blocked I/O; C11 covers the one-slot bound,
not frame/stream/credit budgets; C12 covers finite count/delay and permanent halt,
not jitter or a total-time scheduler; C13 starts an empty model, not a durable
gateway restart; C14 covers ordered invalidation/renewal including a clock-sample
expiry boundary; C15 covers backwards time and unavailable fake freshness, not
real clock synchronization/revocation delivery; C16 validates model limits and
minimal health, not the package configuration schema or a logging pipeline.
Application relay, proof transcripts, real streams and cleanup remain untested.

Result: 49 model tests plus 13 existing frozen-state tests passed (62 total).
Independent review found four model bugs, reproduced and corrected; no remaining
blocking findings within this scope. Exact runs, failures, hashes and limits:
`docs/reviews/2026-10-10-connector-control-model.md` and `.json`.
Stage 1 remains partially complete: the approved model is complete, but the
protocol/wire/identity/limit decisions and executable wire vectors remain open.

## Federation reconciliation and recommended binding (design-only follow-up)

This section supersedes earlier broad statements that connector credentials,
proofs or wire mechanisms are wholly missing. Existing mechanisms are substantial;
the remaining work is their exact binding to the persistent connector role.
The historical mock evidence above is preserved. No model/runtime semantics,
registry values, credentials or authority pins change in this follow-up.

### Inherited authority, not new mechanisms

Detailed approved authority is
`docs/protocol/history/NBSR-WP8-F1-F119-approved-source.txt`: F61 at lines 712–716,
F86 at 1153–1156, active enforcement at 1305–1308, F106 object descriptions at
1830–1857. The pinned historical source, the ratified
`docs/protocol/federation-v0.1-development-profile.md` (2026-08-07), and expressly
approved later corrections govern; the condensed F-number index is supplemental.
Profile-specific values are not blanket production allocations.

- F61 resolves service identity through ownership/delegation, authorized
  destination operator/endpoints and trust evidence to internal OriginSet or
  connector authority inside the Name Plane. No parallel connector directory.
- F106 supplies KeyAuthorizationRecord with exact key purpose, NameOwnershipRecord,
  scoped DelegationRecord, FederationAuthorityProof, FederationAuthorizationContext
  and TypedRevocationRecord. OperatorEndpointRecord publishes federation-facing
  endpoints and excludes private connectors/origins; it is not a registration
  object for the connector. Name ownership and stable Service IDs remain separate.
- Owner/controller cannot sign for another child issuer. Reuse exact-signer COSE
  verification in `nbsr/federation/cose.py`, not bare parsed delegation objects.
  Dependency binding remains in FederationAuthorizationContext beside unchanged
  RouteGrant. Equal version/digest is idempotent; differing digest is equivocation.
- Core v0.2 already has HELLO/ROUTE/STREAM bodies, exact RouteGrant PoP transcript,
  stream-0 framing and source-initiated application streams. See
  `core-v0.2-session-route-schema-proposal.md` and
  `core-v0.2-stream-binding-schema-proposal.md`. These are reusable constraints,
  not proof that the reverse connector role already has an approved mapping.
- `tranche2b-acp-wire-semantics.md` restricts purpose 15 to ACP result signing;
  `tranche2b-enrollment-wire-semantics.md` restricts purpose 16 to enrollment
  results. Do not borrow either for connector registration. Existing purpose 6
  (delegation), 11 (federation authorization) and 14 (federation transport) have
  distinct roles; do not collapse them or allocate a new purpose by assumption.

### Revocation interpretation and mock limitation

Validate issuer authority, exact target/digest, scope, effective time and lineage
using the selected existing profile before applying enforcement. Preserve actual
dependency scope: child invalidation does not revoke the parent or unrelated
services. Terminality, decision outcome and enforcement are separate concepts.

| Authenticated condition | Inherited rule | Proposed connector behavior |
| --- | --- | --- |
| Deny-new-use | No new affected authority/use; not itself a command to kill active flows | Immediately remove dispatch readiness; reject registration, renewal and new flows under that authority. Retain already accepted work only within its existing valid deadlines and policy; retain the owner slot until cleanup, preventing takeover. |
| Terminate-active-use or proven compromise/terminal authority loss requiring termination | Terminate affected active use; isolate unrelated dependencies where safe | Withdraw eligibility first, cancel affected work including blocked I/O, close the affected connection when its own authority is invalid, then release ownership only on confirmed cleanup. |
| Outage/missing fresh evidence without compromise | Do not invent authority; historical rule preserves already valid sessions subject to bounded policy | Reject new acceptance/extension when required evidence is unavailable. Existing work follows its already validated deadline/outage policy; do not translate every lookup failure into compromise. |
| Future-effective or unrelated revocation | Exact time/target/scope controls applicability | Retain verified evidence and schedule effective invalidation; do not terminate early or affect unrelated owners. |
| Temporary hold expires or authority is replaced | No resurrection of terminal target; lineage/tombstones remain | Require fresh validation and a new registration; do not flip an old lease back to READY. |

Core `RevocationMode` in `nbsr/protocol/models.py` uses 1=deny-new and
2=terminate-active. Federation `EnforcementMode` in `nbsr/federation/registry.py`
uses 0=none, 1=deny-new, 2=reauthenticate, 3=drain, 4=terminate-active. **Never cast
between these enums numerically.** Core target_sequence is only valid for a
ServiceRecord target; do not add it to connector revocation because federation
records have generation/sequence. Decode and verify each existing schema intact,
then normalize its semantic result internally with provenance retained.

`TypedRevocationRecord` emergency authority mode 3 is a nonterminal deny-only
mechanism, bounded by its existing Development Profile. Conversely,
`DependencyIndex.enforcement(..., emergency=True)` selects termination and its
test supplies a compromise dependency. These are not interchangeable meanings
of "emergency". The connector adapter must consume the authenticated record and
policy result, not that boolean helper as a universal revocation decoder.
This observation is an integration constraint, not a runtime bug fix here.

At the initial 49-test checkpoint, the mock verifier returned Permission or None;
None immediately stopped and latched
the model for every invalidation. It had no active-flow set or typed enforcement.
Its 49 passing tests therefore **do not prove deny-new-use preservation**. They
remain valid evidence for the narrower immediate-cancel assumption. A future
approved model extension should separate new-use eligibility from active-owner
lifetime and carry typed enforcement. That extension was subsequently approved
and implemented below; the legacy None-verifier path retains its old semantics.

### Recommended exact logical binding

The following is a proposed internal validation/ownership contract, not new wire
bytes. Use existing verified objects and identities; no parallel issuer, trust
store, directory, custom cipher or implicit enrollment.

1. **Resolve authority through F61.** Consume the exact Service Identity,
   ownership/delegation proof and authorized destination from the existing Name
   Plane. Verify the complete relevant trust/freshness/revocation chain. Do not
   publish the connector's private locator through OperatorEndpointRecord.
   Proposed startup uses the configured service's chain through those same
   authority services; it does not wait for a client lookup or invent a client
   RouteGrant/bilateral route context just to register. Per-flow F61 resolution
   and bilateral destination admission remain separate later checks.
2. **Bind principal to connection.** Consume a transport-authenticated peer key
   and gateway identity. Require an explicit verified chain from the exact
   service delegation to that peer key/principal and registration role, bounded
   by service, destination operator/gateway, scope, validity and generation.
   Recommendation: use existing federation key authorization and delegation
   mechanisms if the selected role/action fits them; confirm this mapping before
   implementation. A matching operator alone does not identify a connector.
3. **Build an internal authorization snapshot.** Reference the verified service
   and generation, connector principal/key binding, destination identity, exact
   delegation/proof digests, dependency set/digest, relevant accepted lineage
   floors, validity and enforcement. Consume the existing authorization context
   where its bilateral role applies; do not repurpose it to assert a different
   signer/role or add connector fields to its frozen schema or RouteGrant.
4. **Bind registration to the live connection.** The owner handle combines that
   snapshot with a verified connection instance, session correlation, fresh
   attempt correlation and gateway-local owner generation. Remote acceptance
   must prove the same tuple on the same authenticated connection. A local
   Python object identity is insufficient for wire proof. Reuse existing
   authenticated-control/proof conventions only after the role/transcript
   mapping is reviewed; do not reuse a RouteGrant PoP signature for publication.
5. **Commit conditionally.** Recheck expiry, dependency/enforcement state and
   owner availability at the serialized commit point. Install exactly one
   eligible owner and return matching acceptance. Equal retry of that exact
   accepted attempt may return its existing result without extending lease;
   conflicting payload/correlation or a different live owner is rejected.
   No silent replacement. Late cleanup removes only its exact owner.
6. **Bound lifetime.** Registration deadline is no later than the earliest
   applicable authority/freshness/transport deadline and selected lease cap.
   This is a cap, not a new global timeout. Renewal revalidates dependencies and
   expiry at commit; deny-new-use cannot renew. Reconnect requires a fresh
   connection-bound acceptance and never replays application work. No implicit
   WP4 resume or revival of a revoked registration. Existing active work after
   deny-new-use retains only its preexisting authority; policy must explicitly
   decide whether the registration deadline is also an active-flow deadline.
7. **Keep route admission separate.** Only after live eligible selection may the
   existing destination authorization and exact RouteGrant/channel checks admit
   a flow. Connector registration neither mints a grant nor substitutes source
   approval for the destination decision. Origin addresses remain internal.

Rationale: this minimizes new semantics to connection-bound ownership and
registration lifetime, preserves the existing proof/dependency checks, and makes
the availability cost of one-owner/no-takeover explicit. It does not presume a
new credential type is necessary. Final connector CBOR/messages/stream-role and
proof mapping were not established by the targeted repository/history pass;
that is not proof that no approved artifact exists elsewhere.

### Traceability and proposed acceptance additions

Existing tests below were inspected by name/source, **not rerun** for this edit.
New B-cases are planned and do not increase the historical 49-model-test count.

| Requirement | Governing document | Current code/test or planned acceptance |
| --- | --- | --- |
| Exact-purpose signer and non-widening delegation | F15–F24, F106; Development Profile | `nbsr/federation/cose.py`, `delegation.py`; `tests/federation/test_delegation.py::test_task2_cose_authority_is_reused_for_exact_delegation_purpose_and_signer`; B1 rejects a valid operator key without exact connector service/action binding. |
| Name-plane authority; private connector not a published endpoint | F61/F106; V3.6 identity/flow | `nbsr/federation/discovery.py`; B2 rejects endpoint-record substitution and proves client output excludes origin details. End-to-end connector wiring remains planned. |
| Independent destination and dependency binding | F70–F78; FederationAuthorizationContext schema | `authorization.py`; `tests/federation/test_authorization.py::test_context_binds_every_dependency_and_stays_beside_route_grant` and `test_source_and_destination_authorize_independently`; B3 changes a relevant dependency between verify/commit and rejects admission. |
| Session/attempt correlation and one owner | Core v0.2 session/stream profiles; proposed binding steps 4–5 | `tests/test_connector_control_model.py` covers stale tickets/owners; B4 replays acceptance across real authenticated connections and fails; B5 exact retry is idempotent without lease extension, conflict is rejected. Both wire cases planned. |
| Mode-specific revocation | F86 and active enforcement; Core Revocation schema | `revocation.py`, `registry.py`, `models.py`; B6 deny-new blocks new/renew while preserving an authorized active fixture until its deadline; B7 terminate-active cancels that fixture and releases ownership; B8 maps Core 2 to terminate, federation 2 to reauthenticate, never by cast. |
| Exact target/time and outage | F86; Development Profile timing; historical active enforcement | `tests/federation/test_outage.py::test_known_compromise_overrides_lkg_and_selectively_terminates_only_dependencies`; B9 unrelated/future-effective record leaves unaffected work intact, then applies at effective time; B10 missing freshness denies extensions without inventing compromise. |
| No resurrection/lease overrun | F86/F75; existing lineage rules | `tests/test_connector_control_model.py::test_renewal_cannot_cross_expiry_between_clock_samples`; B11 temporary hold expiry requires fresh registration; terminal target never returns; B12 close failure retains owner and prevents takeover. |

### Decision-ready next boundary

Historical recommendation, subsequently approved only for the bounded slice
recorded below: **a typed-enforcement mock extension** to model
one already-admitted active-work fixture separately from dispatch readiness;
implement B6/B7/B8/B9/B10/B11 using verified-event fakes, preserving all prior
immediate-termination tests. Deny-new keeps only that still-authorized fixture
until its supplied deadline; terminate-active cancels it immediately; missing
freshness never extends it. No real I/O, credential or wire allocation.

Before any authenticated runtime, resolve these exact choices:

- Which existing key-purpose/delegation action and credential binding authorizes
  this connector principal for registration? Prefer an existing compatible
  mechanism; purpose 15/16 and endpoint publication are not substitutes.
- Which approved control-role/schema/proof mapping carries the connection-bound
  tuple? Existing source-to-destination semantics cannot be silently reversed.
- Map registration/new-use expiry, admitted-stream authorization and bounded
  drain to their existing governing profiles. Their separation and controlled
  continuation are already decided; do not reopen a blanket kill-versus-continue
  policy. Identify which deadline is admission-only versus ongoing authority
  before applying any minimum. See the accepted-chronology correction below.
- Which existing profile's timing/freshness values apply to each component,
  and what connector-specific lease/retry cap is still necessary? Reuse applicable
  limits rather than replacing them with new blanket defaults.

No approval of those runtime choices is inferred from the earlier mock approval.

### Approved active-work mock extension — current checkpoint

The user approved one simulated active request with deny-new-use versus
terminate-active-use. `ActiveWork`, `admit_work`, `finish_work` and `enforce` now
extend the existing isolated model. This is still synchronous fake-event input,
not revocation authentication or a wire decoder. No frozen authority or runtime
integration changed. The earlier 49-test report remains historical evidence.

- Deny-new withdraws registration/selection/renewal/new-work eligibility and
  latches this model instance against reconnect. A previously admitted fixture
  retains only its snapshotted authorization/deadline; completion or deadline
  releases it, then cleanup closes the owner. Repeated deny does not extend time.
- Terminate cancels the fixture immediately. Failed/no-op transport close retains
  terminal ownership and blocks replacement; explicit successful cleanup releases
  it. A later deny cannot downgrade termination. Stale owner events cannot affect
  a successor. An event matching the owner at entry still latches reconnect if
  polling concurrently models that owner's expiry/disconnect at the same boundary.
- Every admission requires explicit `lease_bounds_active: bool` and a fixture
  deadline. Both choices cap at admission-time permission expiry; true also caps
  at the existing registration lease. False permits the separately authorized
  fixture to outlive selection eligibility. Tests exercise both; neither becomes
  a real protocol choice. Renewal cannot extend an already admitted deadline
  in this model. Both variants are exploratory fixtures, not equally approved
  normative alternatives; the accepted chronology below narrows their meaning.
- Only exact `EnforcementMode.DENY_NEW_USE` and `TERMINATE_ACTIVE_USE` are accepted.
  Integers, Core enum values and unsupported federation modes are rejected; no
  automatic enum conversion is implemented. Caller supplies an already-verified
  fake event addressed to the exact attempt. There is no persistent revocation
  store: constructing a new model is not proof against process-restart evasion.

Traceability update: B6/B7 have simulated active-lifetime tests; B8 has exact-type
rejection tests, not a Core-to-federation decoder; B9 has stale-owner isolation,
not signed target/scope/effective-time validation; B11 covers no automatic renewal
or reconnect after a latched event in this instance, not persistent tombstones;
B12 confirms retained ownership on throwing/no-op close. B10's outage-preservation
policy remains unimplemented: the legacy verifier None path still immediately
cancels and must not be interpreted as typed deny-new or a production outage rule.
B1–B5 and real event delivery remain at their earlier planned/partial status.

Verification: 72 model tests (49 earlier plus 23 new), 13 frozen-state neighbors
and 24 federation revocation tests passed: **109 total, zero skips**. Independent
review found two boundary defects, both reproduced and corrected; final narrow
review had no remaining blocker. See
`docs/reviews/2026-10-10-connector-active-work.md` and `.json` for all failed runs,
commands, hashes and resource/cleanup evidence. No real-network, crypto or
asynchronous cancellation claim follows from this result. Stage 1 remains partial.

### Documentation-only validation

One scoped self-review checked authority provenance, exact-purpose separation,
the two incompatible numeric enforcement enums, startup-versus-per-flow authority,
mode-specific active lifetime, and preservation of the historical mock claim.
Consistency check passed: all 16 C-cases remain, the current roadmap still has
10 milestones, and all five named test references in the traceability map exist.
The model and test file SHA-256 values still match the earlier implementation
manifest. No runtime tests were rerun for prose changes. `git diff --check` passed
with existing CRLF conversion warnings. An initial multi-file patch failed context
validation and made no changes; the corrected patch succeeded. Existing evidence
manifests remain historical snapshots: their earlier document hashes are not
assertions about this revised draft. AGENTS.md already describes the unchanged
mock-only boundary and needs no further update for this design clarification.

## Accepted chronology: admission expiry is not universal transfer expiry

This correction supersedes the earlier overly broad open-policy framing. **New-use
eligibility, already-admitted stream authorization and bounded drain are distinct
existing decisions.** The missing connector work is an exact integration mapping,
not a new vote on whether downloads should be allowed to complete.

| Authority / sequence | Already decided | Current implementation or test anchor |
| --- | --- | --- |
| V3 directive, section 14 Lifecycle semantics | Stream lifetime may outlive the admission grant within policy; denied renewal stops new streams and applies immediate revoke or bounded completion grace according to signed policy. A large transfer continuing through renewal/rotation is an explicit future acceptance goal. | Architectural direction, not proof that every continuity mechanism is implemented. |
| V3.6-linked `docs/architecture/origin-publication-migration.md`, Safe origin update | Activate replacements for new work; preserve or gracefully drain existing streams. DNS/reachability TTL is not route authorization. | Origin replacement is distinct from WP4 session/channel drain. |
| `docs/protocol/core-v0.2-channel-lifecycle-schema-proposal.md`, approved 2026-08-01, Bounded drain semantics; WP4 decision | This concrete profile bounds drain at 30 seconds and earlier grant/session authority deadlines. No unconditional extension of those profile-specific hard limits. | Existing Rust transport lifecycle; not a universal 30-second download timeout or a connector lease allocation. |
| Accepted F93, August 5; historical approved source lines 1293–1314 | Continue, restricted continuation, drain/reauthenticate or immediate termination according to verified cause/severity/dependency. Ordinary outage does not universally kill active work; compromise/terminate-active enforcement overrides continuation. | Existing federation policy/state machinery; real connector event mapping still needed. |
| `docs/protocol/stream-credit-extension.md`, approved P2D 2026-08-11, Revocation, expiry, close, and cleanup | Expiry/revocation dominates unused credits; already-admitted streams retain established immediate-revoke/completion-grace behavior. | Credit admission must not redefine stream lifetime. |
| August 24 Tranche 6; `docs/architecture/production-go-client/tranche6-resolution-secure-routing.md`, decision 14 and expiry cleanup | Mapping expiry rejects new acquisition, retains active references and does not silently terminate admitted streams. | `client/nbsr-go-client/internal/corestate/mapping.go`: LookupMapping/AcquireMapping reject expired entries; ExpireMappings skips referenced entries; ReleaseMapping removes on final expired release. `mapping_test.go::TestMappingExpiryIsSynchronousAndReferenceSafe`. |
| August 24 Tranche 5; `docs/protocol/tranche5-implementation-status.md`, Generation rotation and Draining and descendants | Atomic A CURRENT→DRAINING/B CURRENT; old accepted work stays on A, no replay/rebinding; finite configured local drain deadline. The adapter's 30 seconds is local configuration, not a universal protocol constant. | `client/nbsr-go-client/internal/session/rotation.go`: markNoNewWorkLocked/startDrainTimerLocked. `rotation_test.go::TestRotateTransportSessionAtomicallyHandsOffAndPinsOldWork`, `TestDrainingDeadlineClosesDescendantsAndReleasesSlot`, `TestRotationDoesNotReplayApplicationPayload`. |

Historical links supplied by the parent, reconciled against these repo anchors:

- [August 5 F93 definition](https://chatgpt.com/c/6a6e213d-9d14-83eb-8963-04889eafc806?messageId=5f3e3fcd-1523-4af8-8325-ce48f696e67e),
  accepted in message `dfe35a29-db3c-4b22-b099-e3aa9a29b2a2` of that conversation.
- [August 24 mapping-expiry definition](https://chatgpt.com/c/6a79d4cd-ee04-83eb-b313-5e14cb212537?messageId=c2ab5860-646d-4f14-bd92-996d67f9cd1f),
  accepted in message `a5e7e0e4-4b4e-4d82-ba8d-e7161b9e79d0` of that conversation.

These are accepted-history references supplied by the parent, not a claim of an
independent reread of the full chats here. The bounded repository inspection
confirmed the quoted distinctions in current docs/code; tests were not rerun.

### Precise model gap and minimal next proposal

`Permission.expires` currently serves both new-use checking and ongoing-work
validity. `_permission()` returns None at expiry, and poll then terminates the
owner. That is meaningful only if this value is an applicable **ongoing authority
deadline**. Treating an admission-only grant or mapping TTL the same way would
contradict the continuity distinctions above. Current passing tests do not resolve
that ambiguity. Neither lease_bounds_active variant establishes the real mapping.

The model has no explicit approved-renewal/completion-grace context. Its fixed
active deadline and None-verifier cancellation must not be read as a normative ban
on renewal continuity or as F93 outage handling. Conversely, a retained admission
snapshot is not permission to ignore ongoing revocation, a hard authority deadline
or the selected profile's finite drain bound. Normal stop/rotation may drain;
there is no accepted guarantee here of waiting without limit for every download.

**Minimal next implementation proposal, not performed here:** first express a
typed fake authorization snapshot that names (a) new-use/admission eligibility,
(b) the already-admitted work's applicable ongoing authority deadline and
(c) an explicitly supplied bounded drain/completion-grace context tied to its
governing profile. Replace the ambiguous model field usage only after this mapping
is recorded; do not add protocol constants, signed fields or a new policy engine.
Focused tests should prove admission-only expiry refuses new work but preserves
the admitted fixture, authorized renewal preserves its binding without replay,
completion or the applicable hard/drain deadline releases it, and authenticated
terminate-active overrides grace with confirmed cleanup. Retain mapping and
rotation source tests as traceability; do not reuse their TTL/drain values as
connector defaults. Real connector lease/credential/wire mapping stays separate.

Documentation check: current roadmap remains 10 stages; no stage completion was
added. Prior 109-test evidence and manifests remain untouched historical snapshots.
This synchronization changes only this profile and the operator plan; model and
test hashes are checked against the active-work manifest. No runtime tests rerun.
