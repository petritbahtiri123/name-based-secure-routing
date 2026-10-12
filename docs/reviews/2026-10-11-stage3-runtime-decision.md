# Stage 3 runtime acceptance boundary and proposed next decision

Status: decision preparation only; no runtime activation or new policy approval.
Follow-up: `2026-10-11-registration-provider-contract-proposal.md` now supplies
the concrete recommended minimal profile and interfaces. It corrects the broad
implication that all registration integration must await full federation threshold
packaging: controller-only operation is an explicit profile choice for approval,
not an already approved fallback. Historical freeze/allocation commits were also
checked; unresolved runtime activation must not be confused with absent design.
This checkpoint follows the positive-revision and gateway CLI CI fixes. It does
not replace the accepted ten-stage plan or reinterpret historical local passes.

## Exact acceptance reconciliation

| Stage 3 requirement | Evidence available | Remaining condition |
|---|---|---|
| Authenticated outbound transport; register and renew without reconnect | The retained 19-case Go/Quinn loopback matrix exercises the development coordinators, real TLS and exporter binding | Current runtime provider composition is absent. Its authority implementation is explicitly SyntheticAuthority and uses logical time 100. The later zero-revision source change has offline tests, not a new live run. |
| Reject wrong identity/service/delegation/generation before dispatch | Existing transport and owner negative tests, signed Python genesis fixture verification, exact pins and revision checks | Connect verified registration authority to the destination owner; signed Python fixture receipts are not a Go/Rust runtime provider. A valid route grant is not registration authority. |
| Exactly one accepted owner; stop removes it only after confirmed cleanup | In-memory owner/ticket tests and real loopback cleanup evidence | Bind the runtime event/clock/transport owner without exposing caller-constructed receipt or invalidation values as trusted inputs. |
| No premature READY | Existing development code creates no production readiness service; model/config distinctions are documented | A configured runtime readiness consumer must derive readiness from current accepted registration and valid provider state, not CONFIG_VALID_OFFLINE or TLS establishment. |

The code supports the stated fixture/development results. It does not support
marking Stage 3 complete. Stage 4 runtime revocation/reconnect acceptance and the
subsequent origin/client/package stages remain downstream. No further test-only
success can substitute for these missing composition boundaries.

## Evidence of the decision boundary

- `docs/protocol/registries/connector-registration-development-v1.json` retains
  `runtime_authorized: false` and `live_trust_authorized: false`. This is distinct
  from the separately permitted isolated development loopback.
- `docs/protocol/connector-outbound-profile.md`, categorized deadline/event
  section: “Because threshold transport packaging is unfrozen, this receipt's
  real producer is a **runtime blocker**”. Raw results, booleans and unverified
  network events cannot create that receipt.
- `docs/protocol/wp8-federation-v0.1-threshold-container.md` is headed
  “PROPOSED DEVELOPMENT PROFILE DECISION - REQUIRES HUMAN APPROVAL”. It also
  explicitly separates wire representation approval from vector/runtime work.
  Some allocation wording refers to approval; that does not establish approval
  of the complete runtime producer. No such approval is inferred here.
- `crates/nbsr-transport/src/federation.rs` seals a route-admission authorization
  carrying a route-grant digest, transport and port. It is not an interchangeable
  connector-registration or revocation receipt.
- `nbsr/connector_registration_authority_offline.py` verifies signed genesis
  fixtures using an explicit signer/inventory and instance-local receipt identity.
  Its own header excludes a hostile-process/runtime authority boundary.

The October 10 federation package-version approval scope concerns immutable v1/v2
packaging and previously approved purposes 15/16. It is not authorization to
repurpose those signing purposes or activate a live connector event producer.

## Concrete recommendation for review

Proceed contract-first with a **development runtime provider boundary**, retaining
Rust destination ownership and Go outbound coordination. Keep the existing
registry and historical authority overlays unchanged until the exact activation
scope and any affected pinned files receive their own reviewed authorization.

The reviewable provider contract should specify:

1. Which existing verified key/delegation evidence authorizes registration-only
   action 24576, and how explicit configured trust is supplied. No ACP/enrollment
   purpose substitution, new trust root, persistent keys or fixture fallback.
2. A verifier-issued opaque receipt bound to exact connection, session, peer,
   request bytes and operation identity, service/gateway, dependency closure,
   positive revision and categorized validity provenance. Preserve serialized
   revalidation immediately before owner mutation.
3. The authenticated event producer's packaging and validation path. Review the
   existing `WP8-THRESHOLD-CONTAINER-01` Option C proposal where threshold evidence
   is needed; keep semantic thresholds, typed enforcement and lineage unchanged.
   Its wire, vector and runtime approvals must remain distinct.
4. Runtime clock/timer dispatch, failed-cleanup retention and readiness ownership.
   Preserve current deadline categories and original drain boundaries; timers
   cannot turn cache freshness into authority or manufacture cleanup success.

After that decision, implement one provider path with the existing independent
verifier negatives first, then compose it with the destination owner under the
already allowed isolated loopback. Acceptance must include altered signature,
wrong purpose/scope, stale revision, expiry, missing provider, correct register/
renew, and confirmed cleanup. Add actual execution to CI only when its harness
exists. Do not label an unimplemented threshold/event path passed.

### Alternatives and tradeoffs

- **Recommended: review and approve the narrow provider/activation contract above,
  then implement it incrementally.** This targets the actual Stage 3 blocker and
  preserves ownership and authority provenance. It requires explicit scope and
  may require a separately versioned source authority if pinned code is touched.
- **Continue offline signed-fixture composition only.** This needs no new live
  trust authority and can help future implementation, but cannot close Stage 3;
  keep the milestone partial. Do not present it as the runtime-provider solution.
- **Create a cross-process Python authority bridge now.** Not recommended: Python
  instance identity would not authenticate IPC, requiring a new transport/trust,
  replay and failure contract. It expands architecture without removing the
  threshold producer decision. Existing route-admission receipts are likewise
  not a shortcut.

## Work completed and not run

Read-only code/design/approval reconciliation and this concrete decision package
are complete. Milestone documentation links this checkpoint. Existing local work
and security checks are preserved. No new behavior was changed, so no regression
suite or expensive build was repeated. No fixture was promoted to runtime trust,
no stage advanced, no live trial/credential/service/deployment operation occurred,
and no push or hosted CI dispatch was made. All work remains local/uncommitted.

Further runtime integration stops here for a material provider/activation decision,
not a resource failure or an assertion that no useful offline work exists. The
already reviewed code and CI fixes remain the independent completed safe work.
