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
