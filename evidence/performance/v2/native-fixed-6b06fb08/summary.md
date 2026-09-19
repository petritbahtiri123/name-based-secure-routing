# Native fixed useful-work port

Source 6b06fb08 ports the existing release binaries' fixed-operation mode to
the native peer wrapper. No production code, protocol, security behavior,
timeout or ACK semantics changed. Historical timed cells remain unchanged.
Both peers declare 1000 operations per stream, zero warmup and depth one.
Live and offline gates require the exact completed count; mixed modes,
simultaneous duration/operation bounds, invalid counts and under-repeated fixed
cohorts reject. Fixed-work cohorts require five counterbalanced pairs.

Literal RED: 10 failures, then an additional under-repeated cohort failed RED.
Final scoped native/fixed/cohort/server-plan suite: 67 PASS; Ruff/diff PASS.
Fresh locked release builds reproduce all three previously retained Linux hashes.

Twenty source/destination cells complete on two internal Docker namespaces as
UID 65532: five Direct/NBSR pairs each for 1 KiB/64 streams and 16 KiB/eight
streams. All pair/cohort integrity gates pass. Every 1 KiB source completes
64000 useful operations (131072000 request/response bytes); every 16 KiB source
completes 8000 (262144000 bytes). Untimed frame-validation traffic is additional.

Diagnostic goodput medians: 1 KiB Direct 1.550956 / NBSR 1.629573 Gbit/s;
16 KiB Direct 2.756195 / NBSR 2.837647 Gbit/s. NBSR 16 KiB residual CV is
10.411%; all five valid observations remain included. These short fixed-work
results are not capacity, latency stability, a speedup, physical-host scaling,
sustained admission, eleven-counter ownership cleanup or wire-overhead proof.

This supplies equivalent useful work for future packet comparisons. Native
capture ownership/readiness, phase separation, offloads, loss-free paired capture
and actual external/server hardware remain separate unclosed gates.
