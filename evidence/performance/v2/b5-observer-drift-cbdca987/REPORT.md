# Near-ceiling ownership observer control: retained abort

Classification: DIAGNOSTIC / INCONCLUSIVE_OBSERVER_QUALIFICATION.
The cohort stopped on its first invalid partial run; no replacement was made.

Clean cbdca987, release, NBSR only, one verified physical core shared by both
roles, 16KiB/8 streams/depth1. Rate is exactly 70% of the matching finite
strict-stable reference: approximately 2810.574 operations/s. Warmup3 seconds,
issue120 seconds, progress30 seconds. The planned three pairs alternated
ownership sampling off/on; comparison gates were absolute median goodput/p99
deltas <=5%, with five repeats for throughput CV >5%.

- off-r1: valid DIAGNOSTIC, 0.710688 Gbit/s, achieved/offered96.4601%.
- on-r1: valid DIAGNOSTIC, 0.728109 Gbit/s, achieved/offered98.8244%, sampled
  ownership coverage and final eleven-counter cleanup pass.
- on-r2: FAIL/partial, automatic goodput drift abort around90 seconds.
  No successful final or post-close ownership proof; owned processes terminated.
- off-r2 and pair3: NOT_RUN after abort, not silently replaced or excluded.

In on-r2 the first/third thirty-second window rates were90.226867 and85.338976
MB/s, a5.417% decline. p99 rose from3.118 to7.0925ms. Errors/timeouts remained
zero in emitted progress. Sampling showed stable live ownership cardinalities;
this does not prove cleanup after the forced abort.

DERIVED tracked-process CPU over approximate thirds:0.748164,0.740171,0.745286
effective cores. The alignment uses the minimum source receipt timestamp minus
source elapsed time, excluding boundary fragments. This cannot identify
competing host activity or frequency/thermal changes, neither of which was
measured. It does not establish a hardware ceiling, production bottleneck,
sampling causality or a leak. No optimization follows from this incomplete
comparison, and no timeout, rate, drift or security threshold was relaxed.

The62-file raw index was verified before preservation. Original raw paths and
actual-byte manifest hash are in analysis.json. Canonical text is separately
normalized/checksummed. Earlier light-load controls and this near-ceiling abort
remain separate; neither is a60/120-minute authoritative soak.
