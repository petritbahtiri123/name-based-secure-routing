# Finite-reference controller cancellation closure

MEASURED RED at 6052fe9f: SIGTERM left both Direct benchmark peers running
with the same PID/start identities and PPid 1. The diagnostic container was
stopped; the incomplete attempt is preserved without replacement.

Minimal harness fix 71c0a3eb uses the shared deferred cancellation handler,
checks registered-child ownership/readiness/observation safe points, and reaps
owned peers through existing finally cleanup. No production/wire/security or
timeout changes. The source inventory now includes the cancellation helper;
the reference acceptance fixture includes the same required provenance.

Three literal RED cases cover server launch, client launch and final observation
before ACK. The first GREEN exposed a synthetic non-increasing timestamp and a
missing new source in the acceptance fixture; both fixture errors and failed logs
are retained. Corrected focused verification: 90 tests PASS, Ruff/diff PASS.

LIVE GREEN at 71c0a3eb: SIGTERM/SIGINT/SIGHUP each seal an invalid reference,
retain InterruptedError, emit no completion ACK and leave both observed owned
PID/start identities absent. SIGKILL is not catchable. This is forced process
cleanup, not graceful runtime-ownership cleanup for interrupted attempts.

The separate normal Direct/NBSR cohort uses 16 KiB/eight streams/depth one,
one selected guest CPU, three-second warmup and twenty-second measurement;
all attempts, counterbalanced order and any five-repeat expansion are retained.
Normal rows/finite classification are in the accompanying JSON. These are
finite Docker/WSL results with an unqualified observer, not a sustained,
server-class or hardware-bound capacity claim. The fresh release build hashes
match prior Rust peers exactly. B3/B4 cancellation remains outside this closure.

All ten normal runs complete without correctness/cleanup failure, but neither
path establishes a strict-stable reference in this cohort. Direct is SATURATED
under the finite latency/dispersion gates (median 2.110116 Gbit/s, CV 23.760%);
NBSR is UNRESOLVED (median 2.079099 Gbit/s, CV 13.183%). This rejects using this
cohort as a near-ceiling soak reference. No run is replaced or discarded, and
no cause is inferred from those classifications alone.
