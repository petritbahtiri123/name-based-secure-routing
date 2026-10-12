# Approved offline counter amendment and milestone alignment

The approved draft-2 amendment removes the four-operation lifetime ceiling:
four completed results are retained separately from replay high-water state and
one pending operation. Session-bound 16-byte IDs encode an eight-byte prefix and
strictly increasing uint64 counter starting at one, independent of directional
envelope sequence. Full-session/peer/service/profile proof bindings remain.
Evicted counters cannot execute again; changed retained bodies reject. Current
acceptance survives result eviction. Renewal/cache eviction preserve ownership
and independently bounded admitted work. Counter exhaustion never wraps.

## Measured validation

- Final scoped Python suite: **358 passed, zero failed/skipped** (103 CRP,
  187 model/federation neighbors, 68 CBOR). Python 3.14.6 does not establish a
  wider supported-version matrix.
- Independent Node verifier: **19 artifact hashes, 34 replay/cache transitions
  across four traces**, plus canonical transcript/exporter checks. This is narrow
  counter-layer conformance, not all 24 lifecycle scenarios or live wire proof.
- Deterministic generator check: 20 package files; 24 executable scenario mappings.
  Ruff check and format check passed.
- Expected red runs retained: renewal ceiling (1 failed), counter contract
  (6 failed), pending-clear cache bound (3 failed). The subsequent scoped green
  runs passed 85, 91 and 103 tests; final neighbors passed 358.
- Initial lint reported two E731 lambda-assignment errors; replaced with named
  functions and final lint passed. That initial tool output was not saved as a
  separate raw log. Intermediate failed source snapshots were not captured;
  exact supervised run logs, final snapshots and a prior-to-current patch are retained.

Independent reviewer found pending-clear paths that could retain five completed
results. Centralized trimming now covers request expiry, invalidation and failed
cleanup. Rereview reported no remaining blocking narrow code finding. Reviewer
inspected code/evidence and did not independently rerun the Python suite.

The original vector package and prior manifests/snapshots remain unchanged.
The new version is `vectors/connector-registration-v1-counter/`. No registry,
ALPN, action or message allocation is inferred from offline fixtures.

## Milestone outcome

**Stage 1 partial; 0/10 complete.** The original ten-stage boundaries are now
summarized at the top of the operator plan with dependencies and acceptance.
The counter decision is resolved. One concrete Stage 1 architectural selection
remains: the Go/Rust component ownership seam and logical gateway location.
Recommended for approval: Rust/Quinn destination gateway owns registration table,
authority-revision commit, accepted handles/quota and cleanup; Go origin connector
owns outbound attempts/retry/renewal through injected interfaces; Python remains
an oracle. Selection belongs to Stage 1; implementation belongs to Stage 3.
No material architecture choice was silently approved by this amendment.

After that selection and contract acceptance, Stage 2 is strict configuration and
zero-side-effect preflight. Real transport/producers/deadlines are later runtime
gates. Registry/carrier approval is a separate pre-wire gate, not permission to
activate anything now. Scope remains one private HTTP service.

## Ownership and limits

All 12 supervised runs reaped their direct children without resource abort.
No task-created containers or background workers were launched. Final suite used
3.62 seconds under the bounded supervisor; disk was 12,202,500,096 bytes at start
and 12,202,504,192 at end, RAM 4,503,744,512 bytes at end. No commit, push,
download, credential creation, deployment or live runtime activation occurred.
Existing unrelated dirty work remains. Hosted CI predates this dirty source and
is not claimed as validation of this change.
