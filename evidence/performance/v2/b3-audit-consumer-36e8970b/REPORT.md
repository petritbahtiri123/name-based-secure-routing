# B3 concurrent setup audit consumer

MEASURED RED: clean 36e8970b release binaries passed five repeats at each
8/16/32/64/128/256 materialized-stream scale. The first 512-stream attempt
failed before active sampling: source authorize_stream_open returned
AuditUnavailable. All raw attempts remain retained; this is not a capacity result.

ATTRIBUTION: the concurrent source and destination setup branches skipped the
existing serial path's per-stream audit consumption until all held streams
completed. The production audit queue is bounded to 1,024 events and fails closed
when full. Stream setup generates mandatory audit events; holding an entire
large batch before consuming them is a harness lifecycle artifact.

SMALLEST FIX: consume queued audit records after each authorized/accepted
concurrent setup operation on both roles, using the same existing pop API as the
serial harness. No production change, event-generation/check bypass, queue-cap
increase, timeout change, workload reduction or wire/ACK change. This fixture
consumer is not a durable production audit sink.

MEASURED GREEN: same 512-stream workload with the retained five-line source
patch passed once, including all eight reported ownership counters zero on each
role. This is a regression proof, not three/five-repeat scale qualification.
Fresh clean-commit scale repeats follow separately.

Verification: release audit::tests::one_channel_can_use_the_exact_global_audit_capacity
PASS, demonstrating the unchanged full-queue rejection and pop recovery;
release source/server build, fmt check and scoped Clippy -D warnings PASS.
One independent focused review found no Important correctness/security findings.
Raw paths, source/binary identities, patch and verified artifact counts are in
external-inputs.json and the retained raw indexes. Windows loopback only.
