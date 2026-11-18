# Go authority deadline and enrollment commit binding fixes

Scope: two reproduced findings, reviewed against development head
`4be57b271cc49b8b06b43180230db502354d4a23` (2026-11-18).

## Changes
- A coalesced caller must not receive a successful reservation after its own
  request deadline. All shared-result return paths recheck that caller's bound.
  Expired request records are not marked complete. Shared provider work and
  remaining valid callers are preserved; this is not a new timer/scheduler.
- The shared enrollment identity commit helper checks the canonical request ID
  and digest before storage, including initial-runtime enrollment. Existing
  wire verification already enforced binding; this was not a demonstrated
  signature or wire-authentication bypass.

## Verification
Both original regression failures were reproduced before fixing. The new
regressions verify mismatched ID/digest rejection without persisted identity,
valid matching enrollment, and expired coalesced caller rejection while the
unexpired initiator succeeds. Existing completion/cancellation and wire binding
neighbors pass. Independent scoped code review found no blocker.

Windows Go 1.26.5: full client module `go test ./... -count=1` and
`go vet ./...` passed with the exact current changed module files materialized
as an overlay over the unchanged tracked client module. Authority tests took
15.435 seconds. Dependencies were offline, build concurrency two.
Tests used a task-owned temporary directory and the existing build cache;
no production ACL allowlist, global permission or toolchain setting changed.

Earlier full-suite attempts in the inherited sandbox temp directory failed
with unapproved-write-ACE/junction/lock-fixture errors. Two representative
failures also reproduced without the fix; both passed using the task-owned
temporary root. The previous failures remain local evidence, not claimed passes.
An inherited cache path also referenced a nonexistent old sandbox directory.

## CI selection and limits
The existing `scripts/ci/check.py` Go profile runs both test and vet on
`client/nbsr-go-client/./...`. No new workflow is necessary: the regression file
is included in this same change. Executed collection confirmed
`TestEnrollmentCommitRejectsMismatchedRequestBinding`,
`TestCoalescedCallerKeepsOwnDeadline` and
`TestEnrollmentCommitAcceptsMatchingRequestBinding`.

Local Windows verification is not hosted Linux/Windows CI or a deployment claim.
Hosted checks must be verified for the resulting commit. No benchmark, VM,
dashboard, main-branch or protocol architecture change is included.
