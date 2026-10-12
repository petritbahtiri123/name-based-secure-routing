# Proposed decision CONNECTED-AUTHORITY-OWNER-01

Status: design for approval; no implementation or activation authorized by this
document. Objective: connect the already verified normal-revocation path to the
existing Rust destination owner, with one governing-context producer seam that
can later support full-model registration. Do not create another service or a
Python IPC authority bridge. Go retains outbound coordination; Rust retains
destination ownership; Python remains an independent conformance oracle.

## Recommended first implementation boundary

Implement a test-compiled native adapter that authenticates the existing normal
Option-C/inclusion-v2 package under explicitly supplied test trust, then applies
its exact typed effect through the existing Gateway and CleanupTicket owner.
The test starts an owner using the existing explicitly synthetic registration
fixture; that setup must remain visibly separate from verified registration.
Positive acceptance means a valid applicable normal termination actually reaches
that owner and retains quota until confirmed cleanup. Invalid evidence must
leave the owner unchanged. This is connected enforcement, not a claim that the
new provider admitted the owner or that Stage 3 is complete.

Why this boundary: the normal package and leaf contract are approved and tested;
controller/emergency full-record packaging is not supplied by this normal-only
v2 amendment. Generalizing its schema silently would invent authority. New-use
permission and READY therefore remain unavailable through the new adapter until
all applicable controller/normal/emergency paths and dependency closure pass.
It is acceptable to enforce an independently authenticated applicable negative
decision without pretending that complete positive authority is established.

Alternative: implement the entire native provider and all three event packaging
paths together. That can follow approved contracts, but first needs explicit
controller/emergency packaging decisions and broader native validation. It is
larger than the next evidenced integration. A Python-issued success boolean or
cross-process receipt is rejected as a shortcut; it would need a new trusted IPC
contract and would bypass independent native verification.

## Governing configuration: what is trusted, what is verified

The sole initial trust input for this slice is a test-owned explicit anchor:
exact existing public signer/key inventory, governing bundle/policy digests,
target-controller mapping, log/witness inventory, organization/control mapping,
dependency inventory and accepted checkpoint floor. No default anchor exists.
Constructor name and report must say `SuppliedTestTrust`; no production config
loader or fallback is added. Its byte inventory is pinned by the test harness,
not learned from the incoming revocation package.

Use existing `FederationTrustBundle` fields for scope, roots, purpose keys,
logs/witnesses, thresholds, supported profiles, revocation sources, staleness and
policy references. The candidate's exact bundle digest must match the supplied
anchor in this first slice. Parse it, check its validity/freshness, key lifecycle,
scope/profile applicability and reference closure before using it. This proves
conformance relative to supplied trust, not cryptographic provenance of genesis.
Key authorization must retain IDENTITY_ROOT signing and the distinct authorized
key purpose; a raw signature result or matching KID is never enough.

The producer derives an immutable accepted context from that anchor and checked
records; network inputs cannot populate trusted FederationAuthority structures,
the eligible roster, organization identities or witness policy themselves.
Normal revocation uses its separately approved policy, not global-trust-v1 merely
because both use 3/5. Full eligible-roster independence is checked, including
unsigned members. Witness requirements remain those of the governing context.

Existing packaging blocks stay CLOSED: `verify_federation_sign1` trust-bundle
rejection, `TrustTransitionBinding`, `SemanticThresholdEvidence.from_transport`,
and every runtime/live registry flag. `TrustBundleStore.accept()` is a lineage
component, never an authenticator. A future authenticated bundle update must
verify the applicable existing global-trust-v1 Option-C policy and all required
log/witness/transition obligations BEFORE feeding that store. No such update is
accepted by this initial pinned-context slice; a new context requires explicit
test initialization, not network-driven rebinding.

## Interfaces and owner mutation

Proposed test-only native interfaces (names are local APIs, not wire fields):

- `LocalAuthorityProvider::from_supplied_test_trust(anchor, clock_snapshot,
  retained_floors)` validates and owns the context. Missing or invalid inputs
  return a typed unavailable reason; no constructor produces permissive defaults.
- `verify_normal_event(package_bytes, owner_view) -> VerifiedOwnerEvent` parses
  the exact approved bytes, uses `connector_signature::verify_exact`, and checks
  Option C, lineage, full-record inclusion, consistency, witness identity/purpose,
  replay, freshness and dependency applicability. The result has private fields
  and no public constructor, deserializer or conversion from bool/Decision.
- `apply_verified_event(provider, gateway, event, clock_snapshot, transport)`
  executes on the same serialized owner path. It rechecks the provider/context
  identity, positive effective revision, event identity, exact owner generation,
  registration, connection/session and dependencies immediately before mutation.
  DENY_NEW_USE uses existing DenyNew invalidation. TERMINATE_ACTIVE_USE invokes
  `begin_cleanup(connection)` and returns/retains its exact CleanupTicket;
  only matching `finish_cleanup(ticket)` after successful confirmation releases
  ownership. It must NOT call `invalidate(Terminate)`/`close_attempt` as its
  termination path: those can release synchronously when no ticket exists.
  Failed completion requires existing explicit retry; cancelled waits do not
  confirm cleanup. No direct owner clearing is added.
- `registration_status(binding)` returns `Unavailable(MissingFullGovernance)`
  in this slice. No positive registration permit or READY can be manufactured.

The existing gateway has only DenyNew and Terminate invalidations. The first
patch must use an explicit Federation-enum match: DENY_NEW_USE maps to DenyNew,
and TERMINATE_ACTIVE_USE starts the retained-ticket path described above.
NONE, REAUTHENTICATE and DRAIN return an explicit unsupported-application result
without owner mutation and keep the new provider unavailable; none is converted
to deny-new or terminate.
This is an incomplete test-only effect adapter, never a full normal-mode runtime
claim. No live owner is put behind it. Full-provider admission cannot be enabled
until those applicable effects have their approved work/deadline semantics too.

The opaque event binds the original R digest and exact typed enforcement, log/
checkpoint floor, applicable dependency set, governing context digest, record
generation/sequence, event ID, effective time and categorized expiry, plus exact
destination owner identity/generation. Target/scope applicability is derived from
the verified record and accepted dependency graph, not an untrusted owner hint.
Wrong-owner replay cannot mutate a replacement owner.

Future positive `RegistrationPermit` uses the same sealed producer, binding all
existing `Binding` fields (profile/action, connection/session, peer, service,
gateway/operator, request digest, dependency digest and policy digest) PLUS
operation counter, provider instance/context digest, positive effective revision,
accepted floor identities and categorized authority/request/registration deadlines.
The gateway's existing final revision comparison is retained and extended to
these exact bindings immediately before mutation. No injected callback, await or
transport operation may intervene after that check. Permits are operation-bound
and cannot authorize different bytes, a reconnect, renewal or owner generation.
This positive permit is specified here but not implemented in the first slice.

## Time, storage, missing trust and readiness

Use the existing injected bounded-clock contract. Check expiry at latest plausible
UTC and apply future enforcement only once earliest plausible UTC reaches its
effective time. Backward/invalid time latches new admission off; it does not
invent termination or release resources. Queue insertion is not an effective
authority revision change. Only an applicable dispatch advances that revision.

Reuse inclusion persistence semantics as the independent Python oracle: exact
record/event bindings, terminal facts, expected restore digest and uncertain
commit behavior. Native in-memory retained state must agree on the same traces.
Do not deserialize a Python snapshot into a trusted native permit, introduce
cross-process storage sharing, or claim the filesystem harness is a production
native store. A later native persistent adapter is separately scoped work.

Missing governing evidence yields an immediate finite unavailable result for
registration/renewal, not an unbounded waiter or automatic fetch. Malformed or
unrelated network input does not itself revoke the current owner. Independently
established authority freshness loss blocks new use; admitted work remains under
its existing independent bounds. A valid applicable termination uses confirmed
cleanup; unavailable positive trust must not suppress that enforcement. Capacity
failure retains owned quota and safety facts, with no eviction/resurrection.

READY is a derived conjunction of accepted registration, current complete
governance, valid time and eligible owner state. It is false for this slice's new
provider. CONFIG_VALID_OFFLINE, TLS, a checked signature or a test trust anchor
alone cannot satisfy it. No runtime readiness endpoint is added.

## Concrete files and selection

Proposed first patch:

- Add `crates/nbsr-transport/src/connector_authority.rs`, compiled only in a new
  integration target; private context/event types and the connected normal path.
- Add `crates/nbsr-transport/tests/connector_authority.rs`; include existing
  signature, codec, registration and cleanup modules using established test
  target conventions. Do not export them from the production library.
- Modify `connector_registration.rs` only for the narrowly reviewed verified-event
  application seam/final owner recheck; preserve existing synthetic fixture APIs
  and their explicit labels. Do not make synthetic Decision a runtime permit.
- Add `scripts/check_connected_authority_vectors.py` and
  `tests/federation/test_connected_authority_vectors.py` as an independent oracle
  composition over existing modules, not a new authority service. Export original
  signed bytes plus expected outcomes and supplied-test-trust identifiers; native
  code verifies bytes itself rather than trusting exported decisions.
- Retain cases under `vectors/connector-authority-local-v1/`, an explicit local
  conformance package version with parent/source hashes and both activation flags
  false. No connector ALPN/message/action change, old registry refresh, frozen
  source-overlay change or new trust-anchor format is proposed.
- Add explicit local Python and Rust test selection to `scripts/ci/check.py` and
  CI contract tests after the target exists; update focused guidance/evidence.

Go coordinator behavior is reused unchanged. Existing loopback harness becomes
the later transport-composition acceptance target after complete native provider
support and fresh socket/test-PKI authorization; no new Go verifier or service
is needed for the first patch.

## Required isolated acceptance cases

1. Existing fixture-created owner receives valid normal 3/5 termination through
   native verification; eligibility withdraws and exact cleanup ticket retains
   quota until confirmation. Failure/cancellation cannot allow replacement.
2. Correct deny-new preserves independently valid active work; exact typed mode
   is never inferred from a numeric cast or changed to stronger enforcement.
3. Invalid signature, 2/5, duplicate signer/organization, common-control roster,
   wrong policy/purpose, scope/dependency/owner mismatch, wrong original leaf,
   stale idempotent checkpoint or missing required witness: zero owner mutation.
4. Same event retry is idempotent; rebound event rejects; old generation/floor
   rejects; changed owner/revision between verification and application rejects.
5. Future event causes no early mutation; unrelated queue insertion cannot cancel
   the applicable event; invalid clock retains ownership and blocks admission.
6. Missing any required positive-governance path, including controller/emergency:
   no registration permit and READY false. No controller-only fallback.
7. A bare TrustBundleStore result, raw CheckedSignature, caller-built Decision or
   Python expected outcome cannot construct the adapter's opaque event.

All first-patch tests are deterministic, local, no sockets/new keys/ACLs or process
kills, using provisioned caches and existing limits. They establish native
connected enforcement under supplied test trust, not Stage 3 completion.

## Decisions requested and remaining gates

Approve this first patch's exact scope: test-compiled connected NORMAL negative
enforcement, independently supplied pinned context, no positive admission/READY,
unchanged production packaging blocks and a separate local vector package.
This is not a request to approve unspecified runtime activation.

Before the subsequent full provider patch, decide the exact controller/emergency
record/proof packaging and governing configuration update/transition adapter;
reuse accepted allocations and deny-only emergency semantics, do not extend
normal-only v2 implicitly. Decide the real clock policy, service-lifetime
retention/compaction and independently provisioned bootstrap/floor source before
runtime acceptance. Process-kill/root/ACL/socket trials each need their applicable
fresh bounded authorization. No new external trust service is prescribed.

The approved filesystem retry already passed root/file ACL checks, real
write/read/reopen and injected post-watermark repair, with exact-root cleanup.
It did not test process death or power loss. Stage 3 remains partial; overall
completion remains 2/10. Full Stage 3 still requires genuine provider-backed
register/renew, wrong-authority rejection, one owner/confirmed cleanup and no
premature READY under all applicable governance. Final pre-pilot audit remains.
