# Linux B3 lifecycle-controller cancellation closure

MEASURED live RED at 9745cecb: SIGTERM leaves both owned lifecycle benchmark
peers alive with unchanged PID/start identities and PPid 1. The diagnostic
container was stopped; the incomplete run remains preserved.

Minimal harness fix f9d8fd1e installs deferred catchable-signal handling only
for Linux execution, propagates cancellation to command/capture safe points,
and checks between lifecycle cells. Existing exception/finally cleanup reaps
owned children. A campaign failure record now accompanies the checksum index.
Windows signal handling, production Rust, wire/security, workload and timeout
semantics remain unchanged. Cancellation during existing marker/readiness waits
is handled at the next safe check; no immediate-response guarantee is claimed.

LIVE GREEN: SIGTERM/SIGINT/SIGHUP each reject and seal the interrupted campaign,
retain the named cancellation cause and leave both observed PID/start identities
absent. No successful lifecycle result is claimed for interrupted attempts.
Forced process cleanup is distinct from graceful zero-owned-resource cleanup.
SIGKILL and host/kernel failure remain outside catchable controller handling.

Three normal repetitions each complete ten same-process open/hold/close cycles
with cleanup PASS, thirty cycles total. This is a lifecycle mechanics regression
check, not a new large-cardinality, fifty-cycle memory-plateau or leak claim.
Normal raw records retain Linux memory/FD/thread/ownership observations. The
fresh locked release build reproduces all three previous Rust binary hashes.

Literal RED tests and 33 focused GREEN tests pass; Ruff/diff checks are retained.
No capacity improvement, qualified soak, physical-host ceiling, security
recertification or final funding freeze is inferred from this harness repair.
