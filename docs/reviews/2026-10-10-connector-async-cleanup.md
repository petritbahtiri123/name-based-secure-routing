# Connector asynchronous cleanup: bounded fixture slice

Base `c7abbc4423a9ad05cea9cdf6678c231a34cafd59` on `codex/nbsr-v3-wp0-wp1`. Uncommitted, no publication.

## Evidence and rationale before implementation

Read the current development review/profile, Core `BorrowedSendCancellation`
and `CreditedAdmissionCleanup` in `quinn_adapter.rs`, the Python model `_cleanup`,
and offline registration `close_attempt`. They establish terminal eligibility
before cleanup, exact ownership, and visible retention until close is confirmed.
Core's locally owned stream/quota drop guards do not establish that an external
asynchronous close has completed. The approved active-work separation still
distinguishes deny-new, termination and finite profile-labelled grace.

The existing Go `Coordinator.Close()` already removes eligibility first and
retains the peer/registration on error. Therefore a small `CleanupPeer` adapter
fits behind `Peer.Close()` without changing the protocol, trust model, active-work
policy or wire registry. No new lifetime/security policy was selected.

## Implemented scope

New `interop/nbsr-go-peer/connector/cleanup.go` and `cleanup_test.go`, both behind
the existing development build tag. One private asynchronous close attempt is
retained; pending/failure returns an error. Completion callbacks only record an
attempt-bound result and notify a channel. Only a later serialized coordinator
close applies successful confirmation and releases ownership. A cancelled or
expired wait neither cancels the backend nor declares quota free. Failed cleanup
requires explicit retry; pending/successful work cannot be retried. First-result
retention and private attempt identity reject duplicate and stale callbacks.

The adapter creates no goroutines, timers, sockets or busy-wait/retry loops.
`begin` is an injected fixture backend contract that must return promptly and
confirm the exact peer. It is not a verified transport receipt. Context controls
only how long the caller waits, not a new protocol cleanup deadline. Existing Go
coordinator, Rust owner, Python models, application grace, source pins and registries
remain unchanged. The retained Rust synchronous cleanup interface is a future gap.

## Validation

Seven new top-level cleanup tests cover immediate completion, pending cancellation,
controlled timeout, cancellation while actually waiting, late/duplicate callbacks,
concurrent duplicate completion, explicit failed-close retry, retained owner/quota,
no replacement/resumed proof before confirmation, and invalid input. Tests use
channels and explicit events, no sleeps. The initial red run was a missing-API
compile failure, not a reproduced live transport bug; it is retained honestly.

Final Go result: **19 connector top-level tests / 67 passing test+subtest events**,
plus **3 CBOR top-level tests / 10 passing events**, zero failures/skips. Parent
test events are included in those event counts. The retained executable repeats
the 67 connector events successfully. Go vet/gofmt and scoped diff checks pass.
Static verification confirms **37 previous implementation sources/vector files**
unchanged and frozen tracked registry/build/transport sources unchanged. Existing
Python 462/Rust 14 results remain historical, not newly run for this Go-only change.
No race-detector run or real backend validation was performed.

Independent review found no blocking ownership/concurrency defect. Its sole
coverage request, cancellation after entering the wait, was implemented and
rereviewed. Exact commands, failures, source/binary hashes and resource results
are retained in the companion JSON and evidence directory.

Seven bounded runs used existing offline caches and at most two workers; all
supervised children reaped, no resource/deadline abort. Final read-only inventory
found zero visible relevant processes. No task-created containers/background
workers, credential/trust changes, network activation, commit or push.

## Remaining Stage 3 work and authorization boundary

Stage 3 remains partial, **2/10 stages complete**. This demonstrates asynchronous
fixture confirmation and cancellation-safe waiting only. It does not prove a real
backend terminates within a bound, nor authenticated revocation, Rust asynchronous
cleanup composition, safe live transport shutdown, durable identity or Go/Rust wire
interoperability. No active application work is introduced or assigned a new grace.

A further code-only Rust cleanup/composition slice can reuse the same ownership
invariants. The next material authorization boundary is choosing/installing real
authenticated transport and authority providers or activating live networking;
any new cleanup/active-work lifetime policy also requires review before selection.
No such activation or policy choice was made here, and this does not start Stage 4.
