# B3 materialization audit consumer: 2048-stream RED/GREEN

MEASURED diagnostic workload: 32 fixed channels, 64 materialized streams each,
one connection/session, unchanged held request, response and ACK semantics.
The existing 2049-bidirectional-stream transport and 32-service authority bounds
permit this workload; no limit was increased.

Literal RED at clean 546b4920 failed application acceptance before active
sampling. A failure-only aggregate snapshot then reproduced the rejection at
zero-based accept ordinal1024: audit current/high-water entries1024, live Quinn
streams1024, authorized application/registry entries2048. The session acceptance
path requires an audit event before committing application admission. The bounded
queue rejected correctly; the fixture consumed this second phase of audit events
only after every held task finished.

Minimal repair: consume existing mandatory audit events after each successful
concurrent application accept. No audit generation/check is bypassed, no queue
cap or timeout changes, no protocol/security/authority/ACK change. The diagnostic
remains failure-only with aggregate counters and fixed labels; timestamp0 is a
phase-only observation, not an elapsed-time measurement. Its counters are global
aggregates, not a per-connection namespace. This fixture consumer is not a durable
production audit sink.

GREEN: the identical2048-stream workload completed once. The destination active
snapshot reports2048 Quinn/application streams and32 channels, followed by all
eight runner cleanup counters zero on both roles. A full repeat ladder is the next
gate; this one-repeat diagnostic is not stable capacity or a hardware ceiling.
All failures, source patches, binary identities and raw hashes remain retained.

Release exact-capacity audit rejection/pop-recovery test PASS; release server
build, fmt check and scoped Clippy-Dwarnings PASS. One independent focused review
found no Important correctness/security issue. This is a harness fix, not a
production performance optimization.
