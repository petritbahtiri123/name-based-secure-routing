# Linux B4 admission-controller cancellation closure

MEASURED live RED at 71c0a3eb: controller SIGTERM leaves the two established
benchmark peers alive with their original PID/start identities and PPid 1.
The diagnostic container is stopped and the incomplete attempt retained.

Minimal Linux-only harness fix 9745cecb installs deferred catchable-signal
handling, propagates its callback into each owned B4 observation backend and
checks at pre-run verification/resource-sampling points. Existing finally
cleanup kills and reaps owned peers and preserves raw stdout/stderr/resources.
Cancellation does not throw from a signal handler between Popen and ownership
registration. Existing readiness/drain deadlines are unchanged; a request
during those waits is handled at the next safe check, not guaranteed instantly.

LIVE GREEN at 9745cecb: SIGTERM/SIGINT/SIGHUP are injected only after all four
established/admission peers are observed. Each run rejects, seals failure
evidence and leaves all four observed PID/start identities absent. This is
forced process cleanup, not graceful eleven-counter cleanup; SIGKILL is outside
the mechanism. No production, wire, security or Windows execution behavior
changes. All three fresh release binary hashes reproduce the prior peers.

Normal verification uses the unchanged finite 512-client, two-source-shard,
125-offered/s workload with concurrent established traffic, one selected guest
CPU, two-second warmup and thirty-second established measurement. Every attempt
and the existing three-to-five-repeat policy are retained. Exact validity,
admissions, performance gates and classification are in summary.json and
normal-records.json. This isolated rate cell does not re-establish a full
stable/degraded/saturated ladder, sustained capacity or host ceiling.

Literal RED and 42 focused GREEN tests are retained. Ruff passes the backend,
Linux entry point and focused tests. The legacy Task4i source-inventory edit
adds the cancellation helper only; its twenty existing Ruff style findings
are identical by rule/message before and after, retained in ruff-existing.json.
No lint rule was disabled and no unrelated formatter rewrite was introduced.
Evidence/privacy/diff validation applies to this package; B3 remains separate.

All five normal attempts admit 512/512 with zero errors/timeouts and cleanup
PASS. Nevertheless this cohort is SATURATED: median actual 104.756154/s versus
125 offered/s (83.805%), with 26.397% established-goodput CV. Median handshake
p99 is 222.628 ms and admission p99 693.526 ms. This does not reproduce the
historical 125/s strict-stable result. The sampled 0.953 effective cores is
whole-run accounting on one guest CPU, not verified host physical-core capacity
or causal proof. Historical accepted results retain their original source and
environment scope; this unfavorable current observation is preserved in full.
