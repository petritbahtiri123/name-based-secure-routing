# Mock federation adapter

Base c7abbc4423a9ad05cea9cdf6678c231a34cafd59, layered on the uncommitted
125-test lifetime correction. No commit or publication is part of this slice.

Boundary: nbsr/connector_federation_model.py reuses AuthenticatedBilateralContext,
AuthorizationEvidence, BilateralAuthorizer, FederationResult, AcceptedFederationObject,
FederationState.apply and DependencyIndex. No federation verifier/state/registry
implementation is modified. Two existing COSE signatures authenticate the test
context, followed by independent source and destination authorization. A bare
FederationResult cannot open or recover ownership. Context digest, dependencies,
owner object and session identity remain exact. Both sides supply current evidence;
a new per-call authorizer prevents its decision cache hiding changed same-time input.

The adapter's one-context outage view starts from a fully verified snapshot;
it is not a durable federation replay/continuity store. F93 existing-context
results retain their enum semantics: fresh cached ACCEPT, RESTRICTED with
REAUTHENTICATE/retry_at, and DRAIN at the development profile's maximum staleness.
Permission.new_use suppresses selection/confirmation/registration/renewal/work
admission while keeping independently authorized work. The fixture deliberately
allows no new use throughout outage; it does not redefine which operations F93
could allow in another profile. Cache freshness is not authority lifetime: the
model separately caps by both signer expiries, both proofs and context validity.
The model's exclusive expiry convention is conservative against the verifier's
inclusive timestamp boundary, not a change to federation's contract.

The existing development profile supplies 300/900-second freshness/staleness and
30-second drain in this labelled fixture only. Grace starts at the original
staleness boundary, not poll time; repeated outage cannot reset it. Fresh complete
verification of the exact context restores eligibility only before existing
registration/drain bounds; it neither replays work nor changes its snapshotted
request limit. Profile-authorized recovery during drain is outside this slice.

simulate_dependency_event is explicitly a fake incident input, not authenticated
revocation delivery. It uses DependencyIndex impact and existing State.apply to
select deny/terminate semantics for an already verified context. It never accepts
a caller's bare FederationResult. Cryptographic threshold/revocation packaging
remains unfrozen: this adapter does not manufacture SemanticThresholdEvidence or
claim that injected incident causes were authenticated. Wrong owner/context and
unrelated dependencies have no enforcement effect. Failed cleanup retains ownership.

Real connector identity/role-to-federation mapping, provenance of ongoing/grace
limits, shared-transport versus service ownership, durable recovery and event
transport remain blocked for runtime use. F93 is reused, not redefined. No new
trust roots, wire IDs, credentials, persistent keys, network or deployment.

Tests use the existing public deterministic Ed25519 seeds and fixture shape in
tests/federation/test_authorization.py, with in-memory signatures and existing
COSE verification. This verifies cryptography on supplied test authorities, not
live credential issuance, discovery, trust-bundle provenance or full enrollment.


## Measured results

- connector-adapter-red: 1 expected failure (module absent), 12 deselected.
- connector-adapter-green: 166 passed including 13 initial adapter cases.
- connector-adapter-boundaries: 19 adapter tests passed; added real-signature
  tampering/wrong-purpose, no bare-result opening, all new-use gates, recovery
  after drain and session-substitution checks. No skips.
- connector-adapter-owner-red: 2 failed, 19 deselected. A distinct rejected
  duplicate transport was not closed; a recovery clock crossing 1049 to 1050
  could replace the old outage snapshot before starting its due drain.
- Fixes: close rejected distinct transport while preserving the same current
  transport; re-poll old eligibility and exact ownership before recovery commit.
  Independent review separately reproduced the boundary and confirmed its fix.
- connector-adapter-final: 174 passed, zero skipped (21 adapter + 88 model +
  65 authorization/outage/revocation/state neighbors), pytest 1.40 seconds,
  supervisor 2.62 seconds. Ruff check/format pass on all four model/test files.
  Independent final narrow review found no remaining blocker; no broad audit.

Final run disk free 12301578240 bytes, RAM free 4467523584 bytes. All supervised
children were reaped with no resource abort. The earlier 19-case run observed
RAM ending at 2615820288 bytes (above the 2-GiB reserve); later runs recovered.
No containers/builds/downloads or persistent credentials were created. Get-Process
showed zero visible Python processes after testing. Supervisor limits remain
95-second work bound, 8-GiB disk start/6-GiB floor, stricter 256-MiB growth and
2-GiB RAM reserve. Cleanup figures are observed, not substituted.

Exact commands/resources and raw stdout/stderr remain under
`evidence/connector-control-model/2026-10-10/connector-adapter-*`. Final adapter,
model and test snapshots plus hashes are retained. Red-run intermediate source
snapshots were not captured; base+commands/logs alone do not fully identify those
intermediate dirty states. Raw pytest trailing whitespace is preserved.
The previous lifetime snapshots/logs/tests remain intact; its manifest describes
that earlier state, not the newer model source with Permission.new_use.

AGENTS/profile/roadmap and current overnight checkpoint are synchronized. Frozen
federation source/tests are unchanged. The existing 125-test lifetime regression
file is byte-identical to its recorded snapshot. Scope remains uncommitted with
no push/bypass, no next-stage work, and unrelated paused-peer/user files preserved.
Published c7abbc44's seven successful CI jobs predate all these local changes.
