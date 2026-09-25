# September25 Go authority-cancellation fixture correction

The full race suite at be07f67c retained a failure in
TestAssembledAuthorityCancellationCreatesNoTransportAndCleansFlow:
PendingCalls=1, PendingWaiters=0 after runtime/opener cleanup. Authority cleanup
was still deferred until t.Cleanup. Twenty unchanged focused runs passed; the
original failed result is retained, not replaced or described as a fixed leak.

Measured/code attribution: Manager.waitPending returns ctx.Err after cancelling
the last waiter's provider context; the separate runPending worker removes the
pending record on provider completion. Existing coalescing tests explicitly await
that idle boundary. The assembled fixture's immediate snapshot raced this worker.

Minimal test-only repair: reuse assertAcquisitionIdle from authority_test.go,
including its existing bounded one-second wait and unchanged zero pending-call /
waiter requirements. No workload/provider timeout, production cancellation,
authority, cache, transport or security behavior changes. No assertion removed.
The separate existing blocked-provider tests retain cancellation/no-transport
and fail-closed checks; no production leak-freedom claim follows from this repair.

Verification: original full-suite RED retained;20 focused race repetitions GREEN;
full demo go test -race -mod=readonly ./... PASS; affected-package go vet PASS;
gofmt/diff checks PASS. One focused parent review checked worker/cancellation
ownership and unchanged zero-counter assertions. Raw logs/commands are retained
in C:/NBSR-build/go-quality-be07f67c, alongside the distinct unresolved frozen
federation manifest-digest failure. No all-Go-green claim.
