# Outbound connector control profile — stage 1 review draft

## Current status — counter amendment

D1–D3 and the session-bound counter amendment are approved for the offline
profile only. Draft 2 is implemented in `nbsr/connector_registration_offline.py`;
current artifacts are in `vectors/connector-registration-v1-counter/`. The old
package and earlier progress sections are historical snapshots. A subsequently
approved separate development registry now assigns the code-only fixture profile
`connector-registration-development-v1`, ALPN `nbsr-connector-dev-1`, independent
envelope version 1, messages 24576..24581 and connector-local register/renew action
24576. See `registries/connector-registration-development-v1.json` and
`../../interop/nbsr-go-peer/connector/README.md`. Production allocations and live
authenticated transport/authority remain unimplemented. The approved Stage 1
ownership selection and corrected stage boundaries are at the top of
`docs/superpowers/plans/2026-10-10-single-instance-operator-package.md`.

A request ID is exactly 16 bytes: the first eight session-ID bytes followed by
an unsigned big-endian 64-bit operation counter. Counters start at one, increase
by exactly one for new operations, and never wrap. Full session, peer, service
and profile binding remains mandatory; the prefix is not authentication.
Operation counters are independent of each direction's envelope sequence.

Keep at most four completed outcomes and one pending operation, plus constant-size
high-water/current-acceptance state. A structurally valid, session-bound new
operation consumes its counter before authority validation; a request rejected
because another operation is pending does not consume the next counter. Exact
retained retries preserve original body, challenge and deadline. Changed bodies,
skipped counters, wrong prefixes and evicted counters reject without execution.
Retained success is returned only while its original eligibility remains valid.
All pending-clear paths enforce the four-result bound. Eviction never withdraws
an owner or separately admitted work; current acceptance digest survives eviction
so subsequent renewal remains possible. Successful renewal does not extend an
independently bounded work deadline. Exhaustion fails closed, with no implicit
wrap, reconnect or takeover policy.

Independent Node validation covers canonical bytes/exporter derivation and 34
counter/cache transitions, not all authenticated lifecycle or live-wire behavior.
The previous interface paragraph deferring production component selection to
Stage 3 is superseded: choose ownership in Stage 1, implement it in Stage 3.
The proposed Python gateway reference is an oracle, not the runtime owner.


**Status: Stage 1 contract accepted; development-only fixtures implemented; live runtime NOT implemented.** This document defines a
review boundary, not a wire standard, new trust root or authority overlay. It
does not change frozen message IDs, ALPN values, signer-purpose identifiers,
credentials or deployment permissions. Only the separate approved development
registry assigns the connector-local fixture identifiers. The later CRP-1 section proposes bounded
lease values for review without allocating or activating them. Existing frozen
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

### Historical model gap and minimal next proposal (before lifetime correction)

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


### Implemented mock lifetime correction — current local checkpoint

This section supersedes the historical Permission.expires/lease_bounds_active
model description above. The isolated fake Permission now explicitly names
admission_expires, active_expires and CompletionGrace(profile, seconds). These
are model inputs, not new signed fields, approved connector defaults or proof
that any real credential has been mapped. The former boolean fixture switch is
removed; an ongoing authority limit can explicitly equal a lease when appropriate,
but the model no longer infers that relationship from registration alone.

Registration/admission expiry withdraws new use and starts finite drain at the
actual expiry instant. Late polling and repeated denial cannot restart the clock.
Work remains bounded by its requested deadline, its ongoing authority and any
started drain. Same-profile shorter verified grace narrows from the original
drain start; longer fresh grace cannot extend an existing drain. A changed profile
is unsupported and fails closed, not silently rebound to a new policy.

renew_work explicitly refreshes ongoing authorization on the same work object,
owner and session before its old bound, only while new-use eligibility remains
valid. Registration renewal alone does not extend work. The caller's request
bound remains fixed. No replay, rebind, resurrection or implicit authorization
occurs. Reauthorization during drain is not implemented; this limited mock path
is not a normative prohibition on a future profile-authorized mechanism.
Deny-new retains only bounded work; terminate-active immediately cancels it and
still requires confirmed close before releasing ownership. None/exception from
the verifier still means invalid/unsupported input, not ordinary outage policy.

Local verification: 125 passed (88 model, 13 frozen-state, 24 federation
revocation), zero skips; Ruff check and format pass. Independent review identified
two defects, reproduced and fixed: ignored grace narrowing and a renewal clock
boundary that incorrectly terminated admission-expired work. Review completion
and exact retained evidence are in docs/reviews/2026-10-10-connector-lifetime-separation.md
and .json. This local patch has not been committed or published.

Separately, published c7abbc4423a9ad05cea9cdf6678c231a34cafd59 passed hosted run
38067741432 with all seven jobs successful. That run predates this local patch.
Stage 1 remains partial; real authority/credential/wire mapping and F93 outage
handling remain unresolved integration work. No other package stage advanced.


### Offline federation adapter — later local checkpoint

The lifetime slice above remains historical 125-test evidence. A separate offline
adapter now consumes the existing AuthenticatedBilateralContext and complete
source/destination AuthorizationEvidence through BilateralAuthorizer. No bare
FederationResult is trusted. Existing FederationState.apply supplies the
existing-context outage outcome; no federation verifier, state semantics, registry
or frozen contract changes. Explicit fixture association preserves exact context,
dependencies, owner and session, without defining connector identity mapping.

A temporary Permission.new_use gate suppresses selection and new-use operations
without cancelling independently valid work. Ordinary outage is no longer
represented as verifier None. Existing-context ACCEPT/RESTRICTED-REAUTHENTICATE/
DRAIN are exercised using the development profile's explicit timing fixture;
independent signer/proof/context expiry still dominates cache freshness. Recovery
requires complete fresh verification of the same context before the old drain
boundary; repeated outage cannot extend deadlines or replay work.

B10 now has bounded outage adapter tests, not production outage integration.
B8/B9 remain limited: exact enums and DependencyIndex-based incident dispatch are
tested, but simulate_dependency_event is caller-supplied fake cause data, not
verified revocation transport or signed target/scope delivery. Real credential
mapping, authority/deadline provenance and shared-transport ownership remain
blocked for runtime. The one-owner adapter has no reconnect/rotation or durable
replay/tombstone store. Unknown profile/real integration choices are not approved.

Verification: 174 local tests pass (21 adapter, 88 model, 65 existing authorization,
outage, revocation and frozen-state neighbors), zero skips; Ruff/format pass.
Self/independent boundary review led to two reproduced fixes: duplicate rejected
transport cleanup and rechecking old expiry before committing recovery. Independent
final narrow review found no remaining blocker. Actual Ed25519/COSE verification
uses existing deterministic public test seeds; no issuance, persistent keys,
network or deployment occurred. See docs/reviews/2026-10-10-connector-federation-adapter.md
and .json. No new commit/push. Published c7abbc44's successful seven-job CI remains
a separate earlier result. Stage 1 is partial, with no new milestone completion.


### Stage-1 test closure checkpoint

A test-only follow-up adds 13 focused cases for destination/proof expiry, two-owner
dependency isolation, changed same-time evidence and timed semantic fixtures.
187 local tests pass (34 adapter+88 model+65 neighbors), zero skips; model code is
unchanged from the 174-test adapter snapshot. Timed fixture scheduling is not
authenticated event delivery. Exact results and the remaining five identity,
acceptance-proof, deadline, ownership and event-delivery bindings are recorded in
`docs/reviews/2026-10-10-connector-stage1-checkpoint.md` and .json. Stage 1 remains
partial; work stops at this review checkpoint without commit, push or next task.


## CRP-1: concrete versioned registration profile proposal

**Status: DRAFT FOR APPROVAL, 2026-10-10.** This section supersedes earlier
unspecified registration recommendations, not inherited policy or historical
187-test evidence. Proposal identifier `connector-registration-v1-draft1` is a
document identifier, not a negotiated protocol value. This is a control-only
profile; it cannot carry origin/application data or authorize stage-5 relay.
No registry, authority pin, credential, source/test or runtime changes accompany it.

### Inherited contract versus proposed binding

Inherited: D7 owner/delegated service authority; F61 resolution through the same
Name Plane; exact-purpose key authorization and non-widening delegation; independent
per-flow destination approval; frozen ConnectorState; V3 section 14/F93/P2D and
Tranche5/6 continuity, revocation and narrow dependency effects. Core RouteGrant,
FederationAuthorizationContext and existing exporter profile bytes remain unchanged.

New and proposed here: a registration-only delegation right, an exact local
principal restriction, connector control exchange and dedicated exporter context,
lease/idempotency/owner rules, and typed internal verification interfaces.
The existing bilateral context belongs to per-flow authorization; it is NOT
mandatory registration evidence and cannot be repurposed as startup authority.
The offline adapter's bilateral fixture is evidence of mechanism reuse only.

Allocation ledger (all unresolved and unusable on live wire):

| Item | Proposal marker | Rule |
| --- | --- | --- |
| Registration action | `UNALLOCATED_CONNECTOR_REGISTER_ACTION` | Means maintain this exact service's registration at this exact gateway; excludes publication, route grants, delegation and application admission. No numeric value selected. |
| Capability/profile discriminator and carrier | `UNALLOCATED_CONNECTOR_PROFILE` | Recommend a separate versioned connector control profile and dedicated negotiated ALPN, reusing transport primitives rather than Core source-role message meanings. Registry/carrier review remains mandatory; never infer support from Core v2 alone. |
| Envelope message codes | `UNALLOCATED_REQUEST`, `UNALLOCATED_CHALLENGE`, `UNALLOCATED_PROOF`, `UNALLOCATED_ACCEPT`, `UNALLOCATED_REJECT`, `UNALLOCATED_WITHDRAW` | Symbolic proposal names only; no alias to HELLO/ROUTE/STREAM codes. |
| ALPN | `UNALLOCATED_IF_REQUIRED` | Recommend a separately assigned connector ALPN for explicit role separation. Its exact token remains unallocated; existing Core ALPN is not a fallback or implementation constant. |

The numeric body keys below are **candidate local field mappings**, not assigned
registry/message IDs. Approval of prose alone does not authorize implementation
or turn the allocation markers into interoperable bytes.

### Authority rule and internal principal restriction

Authorize registration only if all of these hold:

1. The existing verified ownership/delegation chain grants the proposed
   registration action to the connector Operator ID for the exact Service Identity
   and destination Operator, without widening name/service/tenant/region scope.
2. The mutually authenticated peer key matches an ACTIVE, unrevoked
   KeyAuthorizationRecord for that Operator, exact key ID/public key and existing
   FEDERATION_TRANSPORT purpose 14. Delegation signatures retain purpose 6;
   bilateral authorization retains purpose 11. No extra signing purpose is borrowed.
3. Gateway local policy additionally pins `(connector_id, connector_operator_id,
   transport_key_id, transport_key_thumbprint, service_id, gateway_id)` exactly.
   This allowlist only narrows signed delegation; it cannot create missing authority.
   Its canonical configuration digest is `registration_policy_digest`. Stage 2
   validates this configuration; this draft neither provisions it nor signs a
   new object. Unknown/missing pin rejects, with no operator-wide fallback.
4. Complete relevant lineage, freshness, trust and revocation checks pass.
   Digests in a request merely identify evidence; the verifier supplies the full
   verified chain from existing authority providers. Missing evidence rejects
   this attempt; control parsing never creates authority or starts discovery.

This is the recommended narrow first mapping. Registration action allocation is
still required; the current generic action integer parser is not evidence that
any arbitrary action number is authorized.

### Types, canonical bytes and exchange

Use existing bounded deterministic CBOR implementation/profile: preferred encoding,
closed numeric-key maps, unique keys, exact types (bool is not uint), no floats,
indefinite lengths, unsupported tags or trailing data. Framing reuses shortest-form
QUIC varint length plus 1..65,536 CBOR bytes, subject to carrier approval. The
request below is capped at 16,384 bytes; depth 8; dependency/ref lists at 64 entries.
No origin locator, credential private material or application payload appears.

Types: `id16` = nonzero 16-byte bstr; `nonce32` = nonzero unpredictable 32-byte bstr;
`digest32` = 32-byte SHA-256 bstr; `operator32/service32` = the existing federation
32-byte identifier, NOT a cast from Core textual IDs; `text64` = 1..64 ASCII bytes
matching the existing identifier grammar; `uint64` = 1..2^64-1;
`time` = uint Unix seconds 0..253402300799. Overflow rejects before arithmetic.
Core/federation identity conversion must use the existing validated identity
provider, never string hashing or truncation.

Carrier metadata MUST include nonzero `session_id:id16`, `request_id:id16` and
strictly increasing per-direction sequence. Session ID is connector-generated
fresh per authenticated connection; request ID fresh per new operation. The
connector is the QUIC client and opens the first bidirectional stream (0) after
mutual TLS completion. The gateway responds on that stream. Exactly one control
stream; no second control stream, 0-RTT, datagrams or application streams in CRP-1.
Future relay stream initiation is a separate stage-5 profile, not reversed Core
STREAM_OPEN semantics. A control-only success proves registration, not a download.

`REQUEST` body (all keys required, closed):

| Key | Named field | Type / constraint |
| ---: | --- | --- |
| 0 | body_version | uint exactly 1 |
| 1 | operation | text exactly `register` or `renew` |
| 2 | connector_id | text64; exact local principal pin |
| 3 | service_id | service32; exact delegated service |
| 4 | connector_operator_id | operator32; exact authenticated peer authority |
| 5 | gateway_operator_id | operator32; exact authenticated destination |
| 6 | gateway_id | text64; exact authenticated destination identity |
| 7 | transport_key_id | bstr 1..64, exact peer key authorization |
| 8 | transport_key_thumbprint | digest32, SHA-256 of authorized raw Ed25519 public key |
| 9 | key_authorization_digest | digest32, existing federation canonical-record digest |
| 10 | authority_refs | sorted unique array of 1..64 `[object_type:uint(existing registry), record_digest:digest32]`; includes ownership/delegation and relevant policy/trust references |
| 11 | dependency_digest | digest32, SHA-256 of deterministic CBOR authority_refs; verifier checks completeness, not only matching hash |
| 12 | registration_policy_digest | digest32, exact accepted restrictive local configuration |
| 13 | requested_lease_seconds | uint 1..60 for this proposed bounded profile |
| 14 | sent_at | time, inside selected authenticated clock-skew policy |
| 15 | previous_accept_digest | null for register; digest32 of current ACCEPT for renew |

`request_digest = SHA-256(CBOR(REQUEST body))`; evidence digests use each existing
object's defined digest domain, not an arbitrary hash of a COSE wrapper. Existing
object generation/sequence floors are checked from verified objects; no second
connector authority-generation counter is invented.

`CHALLENGE` keys: 0 body_version=1; 1 request_digest:digest32;
2 gateway_nonce:nonce32; 3 challenge_expires_at:time. It echoes carrier session
and request IDs. An exact pending REQUEST retry returns the identical CHALLENGE body
and original expiry; it never generates a replacement nonce or restarts the timer.
One outstanding challenge per connection, valid at most 5s and
never past authority/connection validity. It is bound internally to this exact
peer, REQUEST bytes and live connection. Receipt grants no registration.

Reuse the existing TLS 1.3 exporter primitive (`quinn_adapter.rs` and the WP4
exporter conformance mechanism), with a **new proposed domain**, never the frozen
Service Channel label/context. Proposed label ASCII:
`EXPORTER-NBSR-Connector-Registration-v1`; output exactly 32 bytes. Context is the
exact deterministic CBOR array:

```text
["NBSR-CONNECTOR-REGISTRATION-CONTEXT-v1", 1,
 session_id, request_id, request_digest, gateway_nonce,
 connector_operator_id, gateway_operator_id, gateway_id,
 transport_key_thumbprint, registration_policy_digest]
```

`PROOF` keys: 0 body_version=1; 1 request_digest:digest32;
2 gateway_nonce:nonce32; 3 channel_binding:digest32 (the exporter output).
The gateway computes and compares the same output on this live TLS connection,
then consumes the challenge once. The binding is not a signature, independent
credential or publication authority; it is sent only inside the protected control
channel and must not be logged/exported as audit evidence. No application key,
new key type or custom KDF is added. Exporter unavailable means unsupported;
there is no TLS-success-only fallback. Exact derivation/domain review and vectors
are mandatory before enabling this new use of the established primitive.

### Serialized acceptance, ownership and renewal

At proof commit, recheck all authority/dependencies, challenge expiry, connection
liveness, restrictive configuration digest and one-owner availability. Gateway
owns the atomic table entry keyed by `(service_id, gateway_id)`. No takeover.
Rejecting a different attempt must not close the existing owner's connection.

`ACCEPT` keys (closed): 0 body_version=1; 1 request_digest:digest32;
2 registration_id:id16 (gateway-generated); 3 gateway_epoch:id16 (fresh per gateway
process incarnation); 4 owner_generation:uint64 (strictly increasing within epoch,
no wrap); 5 accepted_at:time; 6 lease_expires_at:time; 7 renewal_due_at:time;
8 dependency_digest:digest32; 9 registration_policy_digest:digest32.
Define acceptance digest exactly as:

```text
accept_digest = SHA-256(CBOR([
 "NBSR-CONNECTOR-ACCEPT-DIGEST-v1", 1,
 session_id, request_id, ACCEPT_body
]))
```

The existing deterministic CBOR profile applies; the body is the complete closed
map above. Envelope sequence/framing are excluded, so a retransmission can advance
the sequence without changing this digest. `previous_accept_digest` and
`current_accept_digest` both use this definition. "Identical ACCEPT" means identical
canonical body bytes and correlation IDs, not identical envelope sequence bytes.
Client validation requires a positive bounded interval, nonfuture accepted_at
beyond the permitted skew, and `now < lease_expires_at`; an already expired
response never makes READY.

All carrier correlation and request/dependency/policy digests must match. The
connector becomes READY only after validating this response on the same connection.
An owner handle is `(live connection, session_id, registration_id, epoch, generation)`.
Epoch is correlation, NOT identity/authority generation or a substitute for durable
federation floors. Restart loses live ownership; old acceptances never authorize a
new connection. Cleanup compares the complete handle and releases only confirmed
resources. Failed close retains terminal ownership; it cannot report a free slot.

`lease_expires_at = min(accepted_at + requested_lease_seconds, verified admission
authority/freshness ceiling, live transport deadline if one applies)`; result must exceed now.
`renewal_due_at = accepted_at + floor((lease_expires_at-accepted_at)/2)`; if the
interval is one second, renewal_due_at equals accepted_at and no extension is
promised. Proposed default request is 60s, not a protocol-wide transfer lifetime.
Renew uses the same exchange with a new request ID and previous_accept_digest.
It requires the exact current owner, fresh proof and full revalidation before the
old lease expires. It retains registration_id/epoch/generation and replaces the
acceptance; it does not replay application work or extend active-work authority.

Exact duplicate PROOF/REQUEST on the same connection, with retained request ID
and byte-identical digest returns the same canonical ACCEPT body only if it is
still the CURRENT acceptance of that exact live, eligible owner and its lease
has not expired. No second commit, generation increment or deadline reset.
A superseded acceptance (including an old register result after renewal), denied,
revoked, withdrawn, disconnected or expired owner cannot return success from the
cache. Use REPLAY for superseded correlation and the applicable authority/lifecycle
rejection for invalidated ownership; never reauthorize from a cached response. A conflicting digest is replay.
Keep at most four completed correlation results plus one pending request; expired
results can be evicted while retaining the monotonic sequence watermark. A result
no longer retained is rejected, never recomputed from an old request. Repeated
wire retransmission uses a new envelope sequence but the same request ID/body.
Same sequence is replay. Cross-connection copies fail live exporter/correlation.

`WITHDRAW` keys: 0 body_version=1; 1 registration_id:id16; 2 gateway_epoch:id16;
3 owner_generation:uint64; 4 current_accept_digest:digest32. Same live owner only;
withdraw eligibility immediately, then follow the applicable bounded drain/close
policy. No replacement owner until cleanup confirms release.

### Categorized deadlines and verified event boundary

The verifier returns explicit categorized deadlines with provenance references:

| Category | Source and enforcement |
| --- | --- |
| Admission authority/freshness ceiling | Earliest applicable verified key/delegation/policy registration validity and freshness restriction. It EXCLUDES the existing registration lease. The lease is separately bounded by this ceiling; renewal must commit before the old lease expires but may extend the new lease up to the freshly verified ceiling. Neither value is an ongoing hard limit unless another applicable profile independently makes it one. |
| Ongoing hard deadline | For later flows, the applicable approved RouteGrant/channel/session and federation context policy. The verifier identifies which dependencies remain required throughout use. CRP-1 has no application work and does not invent an ongoing grant at startup. |
| Drain cutoff | Earliest existing ongoing hard limit and `drain_start + applicable profile bound`. Reuse WP4's 0..30s only for WP4 channel drain, or the explicitly selected development-profile bound. Origin/mapping TTL does not become a universal active-transfer cutoff. |

Current registration lease is a separate owner property, not verifier authority.
Each internal authority/drain deadline carries `(category, expires_at, governing_profile,
verified_record_refs)`. Missing/ambiguous provenance rejects the requested new
operation rather than guessing. Earlier valid work follows its already accepted
policy. Clock skew never increases a hard deadline. Use existing record/profile
inclusive/exclusive rules in their validators; select only while `now < lease_expires_at`.

A runtime dispatcher may consume ONLY an internal verified event from the existing
authority subsystem: `(record_digest, issuer/authority validation receipt,
exact typed target+target_digest, scope, effective_at, validity, lineage,
EnforcementMode, affected_dependency_closure, accepted_state_revision)`.
These are internal fields, not a new signed object or proof substitute. Derive
closure through DependencyIndex and recheck revision at serialized dispatch.
Future-effective events wait without effect; stale/unrelated events cannot affect
an owner. Repeated drain never resets its original cutoff. Terminate overrides
grace and cancels only dependent resources; transport-key compromise covers all
owners dependent on that transport. Deny-new stops new admissions/renewal and
preserves independently valid bounded work. Fresh outage recovery revalidates
before restoring new-use eligibility; it never clears terminal tombstones.

No raw FederationResult, parser success, caller boolean or unauthenticated network
event can create the receipt. Existing semantic revocation thresholds remain
unchanged. Because threshold transport packaging is unfrozen, this receipt's
real producer is a **runtime blocker**, not implemented by CRP-1. Pure/vector
fixtures may explicitly synthesize it and must be labelled as such.

### Rejection, failure states and resource bounds

`REJECT` keys: 0 body_version=1; 1 request_digest:digest32;
2 protocol_error: existing frozen ProtocolError. Carrier request/session correlation
must match. If the request cannot be safely decoded/correlated, use the approved
carrier's generic error behavior after carrier selection; no partial ACCEPT.
No origin details, raw credentials or exporter values in errors. Proposed mapping:
malformed/unsupported -> PROFILE_UNSUPPORTED; absent/untrusted authority ->
RECORD_UNTRUSTED; stale -> RECORD_STALE; revoked -> RECORD_REVOKED; wrong role/scope
-> ROUTE_DENIED; bad binding -> PROOF_INVALID; reused/conflicting correlation ->
REPLAY; occupied owner/pending capacity -> OVER_CAPACITY; cleanup/internal failure
-> INTERNAL with eligibility withdrawn. Names refer to existing frozen errors,
not new codes; mapping itself needs profile approval. Specificity never leaks keys.

Proposal limits: one accepted owner per service/gateway; one outstanding operation
per connection; zero waiting registrations; four retained operation results;
5s challenge/registration exchange deadline including response; three connect
attempts per explicit start with 1s then 2s backoff, no hidden infinite retry;
60s maximum requested registration lease. Authority/scope/revocation failures do
not auto-retry. Transient connect failures may consume the remaining bounded
attempt budget. Any stricter governing transport/authority bound wins. Connection
rejection/timeout closes only task-owned attempt resources; cleanup failure is visible.

Failed pre-READY attempts use a separate terminal attempt result. Do not fabricate
AUTHENTICATED/READY or add frozen lifecycle edges to reach DRAINING. Successful
READY owners use the legal DRAINING -> DISCONNECTED path after confirmed cleanup.
This separation is the recommended explicit design choice requiring approval;
all application replay, takeover and automatic resurrection remain excluded.

### Accepted component interfaces and implementation/test inventory

Future runtime paths below are selected but not created in this offline slice.
Existing Go internal packages must not be imported across module boundaries.

The user approved the Rust destination gateway / Go origin connector / Python
reference division. This inventory supersedes the earlier Python gateway-location
proposal and selects component placement, not permission to activate wire traffic.

| Location | Responsibility / interface | Stage |
| --- | --- | --- |
| `nbsr/connector_registration_offline.py`, `tests/protocol/test_connector_registration_vectors.py` | Existing serialized reference oracle: request/proof/withdraw, revision guard, typed invalidation, timers and ownership. Fixtures are not authenticated producers. Replaces the proposed `services/connector_registration.py`; do not create a duplicate coordinator. | 1 evidence |
| `scripts/generate_connector_registration_vectors.py`, `scripts/verify_connector_registration_vectors.mjs`, `vectors/connector-registration-v1-counter/manifest.json` | Existing deterministic draft-2 bytes, 24 scenario mappings, independent transcript/exporter and counter/cache checks. Original package/proposal remain historical. | 1 evidence |
| `client/nbsr-go-client/internal/connector/profile.go`, `profile_test.go` | Pure registration types, closed parsing, response/correlation validation against the accepted profile. No networking or key creation. | 3 implementation |
| `client/nbsr-go-client/internal/connector/authority.go`, `authority_test.go` | Inject existing authority evidence and validate response bindings; never grants destination publication itself. Exact principal/service/policy/dependency/deadline references cross the seam. | 3 implementation |
| `client/nbsr-go-client/internal/connector/lifecycle.go`, `lifecycle_test.go` | Go origin owns attempts, retry/correlation and renewal. Separate terminal failed-attempt outcomes; no implicit takeover or work replay. | 3, then 4 |
| `crates/nbsr-transport/src/connector_registration.rs`, `crates/nbsr-transport/tests/connector_registration.rs` | Rust destination owns service-keyed registration table, `TryCommit(candidate, expectedRevision)`, `Renew(owner, expectedAccept)`, `Withdraw(owner)`, `ApplyVerifiedEvent(event)`, accepted handles, quotas/dependencies and confirmed transport cleanup. Destination authority validation remains independent. | 3, then 4 |
| `client/nbsr-go-client/internal/adapter/connector_control.go`, `connector_control_test.go`; `crates/nbsr-transport/src/connector_control.rs`, `crates/nbsr-transport/tests/connector_control.rs` | Narrow `AuthenticatedPeer`, control send/receive, `ExportBinding(label, context, 32)` and `CloseOwner` adapters over existing transport primitives. They do not manufacture authority. | 3 implementation after pre-wire approvals |

No Go internal-package imports across module boundaries, second crypto stack or
new gateway daemon is selected. The logical gateway is the destination role;
Stage 2 supplies its configured endpoint, Stage 7 packages it, Stage 10 approves
actual placement. Wire allocation and any pinned-source authority change require
their separately reviewed gate before Stage 3 activation. Real producer/clock/
transport integration and independent wire conformance are not claimed by Stage 1.

### Service-keyed extensibility without widening the first slice

User direction accepted the narrow first slice and requires easy later addition
of services. Implement no service-name switches, fixed global service ID or
service-specific identity logic in framing, verifier adapters or lifecycle code.
Use `ServiceRegistrationConfig` entries keyed by `(service_id, gateway_id)`, each
holding the exact principal restriction, authority-policy references, lease/quota
limits and an origin target reference kept only in origin-side configuration.
The first version validates exactly one enabled entry; this is an outer capacity
policy, not a different identity algorithm or hardcoded singleton inside the core.

Every owner, accepted work reference, quota reservation and dependency-index entry
carries its service key and exact owner handle. Core operations take that key;
no lookup by connector display name alone. Service-specific authorization remains
mandatory even if two services share one Operator or a future transport. A global
resource ceiling bounds the sum; each service has its own lower quota. A transport
dependency is explicitly shared, never implicitly merged with service dependencies.

Future additional configuration entries may reuse unchanged REQUEST fields and
per-service ownership logic only after the carrier advertises/approves the larger
capacity and existing total/per-service limits are enforced. Adding a service
must not change canonical bytes for existing service A. A new wire field, new
operation/right, altered proof domain or changed acceptance semantics requires a
new reviewed profile version; unknown versions/fields reject without fallback.
No plugin system, dynamic handler discovery, multi-tenant control plane or generic
framework is required. Origin protocol expansion belongs to the later relay stage.

Testable design criterion: run the same coordinator/verifier interfaces with two
explicit fixture service keys A and B and independent authority/dependency/quota
inputs. Filling, rejecting, renewing, withdrawing or revoking A must not mutate
B's owner generation, eligibility, quota or deadline. A transport-wide compromise
must affect both only when both explicitly depend on that transport. The first
runtime configuration still rejects two enabled services until separately approved.
Vector CRP-24 below is a pure coordinator extensibility test, not permission to
activate multiple services or evidence that shared-transport isolation exists today.

### Vector proposal and approval gate

The accompanying JSON enumerates **24 finite cases** with exact expected ownership
and eligibility outcomes. It is a design manifest, not a conformance package.
After allocation/profile approval, each case must identify canonical inputs,
full fixture authority, connection/exporter fixture, expected outputs/error,
owner counters, byte lengths and hashes. Require one independent decoder/verifier;
no expected signature/exporter value is self-certified solely by its generator.

Three concrete decisions for profile review (the user has accepted the narrow,
service-extensible direction; exact wire/allocation approval remains separate):

- **D1 — authority:** approve registration-only delegated operator authority PLUS
  exact gateway-local key/principal restriction; no new root/key type and no
  operator-wide implicit registration. Tradeoff: key changes require explicit
  verified/configured binding updates instead of convenience fallback.
- **D2 — exchange/ownership:** approve the dedicated proposed TLS-exporter context,
  control-only stream roles, one owner/no takeover, exact idempotency and separate
  failed-attempt outcome. Tradeoff: bounded availability during cleanup; no claim
  of relay interoperability until its later profile. This authorizes finishing
  allocation/conformance review, not live transport use.
- **D3 — bounded profile:** approve the proposed 60s lease/5s exchange/three-attempt
  limits and provenance-based deadlines; retain inherited continuity/F93 policy.
  Tradeoff: conservative startup/retry behavior; active transfers are not assigned
  a universal 60s/30s timeout.

Stage-1 checklist: inherited-policy reconciliation PASS; 187-test model evidence
PASS (historical, unchanged); concrete proposed fields/transcript/inventory PRESENT;
D1-D3 approval PENDING; carrier/action/message allocation PENDING; executable
success/negative vectors and independent conformance verification PENDING; final
profile/interface acceptance PENDING. Stage 1 remains partial, 0/10 complete.
No profile approval, runtime authorization or publication is inferred from this draft.

## CRP-1 offline implementation checkpoint (2026-10-10)

The user subsequently approved D1-D3 for **offline specification and executable
vectors only** (approval relayed from Sentinel_f51491cf36dc8191b41de0964dbf6622).
The preceding proposal and its review hashes remain historical. This approval
does not assign action, message, profile or ALPN identifiers and does not activate
runtime authority, credentials, networking or publication.

Implemented `nbsr/connector_registration_offline.py`: bounded candidate body
schemas, framing, exporter context, ACCEPT digest/client validation, service-keyed
restrictive pins, single-owner registration/renewal, exact current retries,
withdrawal, explicit candidate/owner cleanup and dependency-denial fixtures.
The synthetic authority receipt is bound to request, connection, session,
admission ceiling/provenance and revision. A read-only revision snapshot and a
final clock sample guard serialized commit. It is not an authenticated receipt
producer. No application work or transfer deadline is introduced in this module.

`vectors/connector-registration-v1/manifest.json` maps all 24 proposal scenarios
to executable pytest nodes. Eighteen retained byte artifacts plus the manifest
include canonical bodies, framed REQUEST, public deterministic TLS exporter
input/output, transcript, ACCEPT digest and negative encodings. Existing
connector model/adapter tests explicitly supply the continuity, outage and
semantic-event scenarios. They remain distinct from the new registration codec:
no claim of an integrated live download or cryptographic registration-action
proof follows from the mapping. CRP-09 exercises verifier rejection/revision
guards, not a new durable registration lineage implementation.

The independent Node implementation checks artifact integrity, canonical
transcript, TLS 1.3 SHA-256 exporter derivation, framing, ACCEPT digest and selected
negative fixtures. It does not independently execute all 24 stateful scenarios.
Final scoped Python result: **338 passed, zero failed/skipped** (83 new CRP tests,
the previous 187-test scope freshly rerun, and 68 strict-CBOR neighbors). See
`docs/reviews/2026-10-10-connector-registration-offline.md` and its manifest for
commands, failed attempts, source hashes and resource/cleanup evidence.

### Remaining Stage 1 gates

The four-result cache exposed an unresolved long-lived replay question: after a
random request ID is evicted, an increasing envelope sequence alone cannot tell
an old operation from a new one. The offline model conservatively retains four
operation slots and rejects further operations. It does not implement eviction,
unlimited renewal, automatic reconnect or takeover. A reviewed bounded replay
strategy is required before a long-lived runtime; no new wire choice is made here.
Explicit `poll()` drives fixture expiry/cleanup; there is no asynchronous timer
or authenticated event dispatcher. Clock skew zero and the additional unowned
candidate slot are labelled local fixture choices, not production allocations.

Stage 1 remains **partial; 0/10 stages complete**. D1-D3 offline approval and
bounded offline scenarios are complete. Registry/carrier allocations, complete
authenticated registration-chain vectors, safe long-lived replay retention,
production clock/deadline policy, real event-receipt producer, independent
stateful/wire conformance and final profile/interface acceptance remain open.
