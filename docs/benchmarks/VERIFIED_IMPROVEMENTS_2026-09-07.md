# Verified improvements and remaining closure

Evidence review at `74c2058c81c45406d0cfefdcc01a10ee049d1766`.
Scope: continuation from `ba8c93472969d8ecf13dac2b3322694e209d1d2d`.
Status: PARTIAL; this is not a final funding freeze.

## What actually improved

| Change | Demonstrated benefit | Claim boundary |
| --- | --- | --- |
| Finite Linux exit-transition sampling | Identity-checked handling of an observed process-exit race; 500 child lifecycles checked | Ordinary live telemetry errors remain failures |
| Failure context and source binding | Traceback notes survive; shared formatter and dirty-source preflight prevent misleading provenance | Measurement integrity, not throughput gain |
| B5 latency-buffer preparation | Bounded sample pages are resident before timing; focused residency regression passes | Removes delayed benchmark allocation residency; does not reduce production memory |
| B3 source join before cooldown | Existing wait occurs before sampling intentionally exiting bundle sources; five repeats each at 256 and 512 complete | No timeout increase; 1024 remains unsuccessful |
| Started-descendant cancellation test | Five repeated test pairs verify cancellation after child startup and prompt executable release | Stronger regression coverage, not a new production implementation |
| Canonical/raw evidence repair | Separate indexes, retained logs and byte-preserving Git attributes bind actual artifacts | Unfavorable and interrupted attempts remain preserved |

No production NBSR optimization or new production speedup was demonstrated in
this continuation. Frozen protocol/security semantics were not changed.

## Newly demonstrated scale

MEASURED, Linux WSL2/Docker loopback, release binaries:

- At `1c16b03d`: 2048 materialized streams, with five repeats at every tested
  count from 32 through 2048. This is demonstrated test scale, not a ceiling.
- At `d0792699`: 512 authenticated connection/session/channel/stream bundles,
  five repeats; five repeats also pass at 256. All completed rows have final
  zero ownership.
- Three completed same-process runs of 50 cycles each: 150 cycles, CLEAN
  recorded ownership, zero first-to-last FD/thread deltas for both roles.
  The fourth attempt was interrupted for budget and remains retained.

DERIVED from the sealed analyses: combined active private-resident stream slope
is about 39,521 bytes/stream (32–2048, `1c16b03d`). Combined active bundle slope
is 666,176 bytes/bundle (256–512, `d0792699`, only two scale points).
These include both benchmark endpoints, secure transport and runtime/fixture
costs; they are not isolated NBSR object sizes or evidence of memory reduction.
Do not combine source stages into one fit.

## Lifecycle memory assessment

Final cooldown private-resident values across the three 50-cycle repeats:

| Role | Values (bytes) | Sample CV |
| --- | --- | --- |
| Source | 9,146,368 / 9,011,200 / 9,113,600 | 0.776% |
| Destination | 6,041,600 / 6,189,056 / 5,943,296 | 2.042% |

Endpoint footprint dispersion is below 5%; this does not qualify every growth
metric. Source first-to-last increases are 3,170,304–3,219,456 bytes; destination
increases are 122,880–299,008 bytes. Destination second-half slopes range from
-851 to +9,638 bytes/cycle. The retained-memory cause remains INCONCLUSIVE;
neither a leak nor bounded allocator retention is established. Further repeats
and attribution are required before a strong memory-stability claim. Do not
substitute final ownership zero for absence of retained memory.

## Remaining engineering

1. The 1024-bundle attempt fails connection ACK collection after release.
   Retained detail also includes `B3 application accept failed at ordinal 0:
   ApplicationStreamFailed`. These observations do not identify the causal
   origin; do not label this a measured hardware or production ceiling.
2. A qualified 60–120 minute near-ceiling soak remains NOT_PROVEN. The B5
   pre-touch rerun still failed a private-growth gate; intrusive mapping traces
   were not observer-qualified for performance attribution.
3. One deferred Administrator capture is listed in
   [ADMIN_REQUIRED_FINAL_VALIDATION.md](ADMIN_REQUIRED_FINAL_VALIDATION.md).
4. External server/NIC/WAN validation requires unavailable hardware. Local VM
   results do not substitute for it.
5. Accepted private-origin isolation and federation admission preflight remain
   scoped evidence. Live runtime federation is not implemented.

The practical improvement is a more trustworthy benchmark, wider demonstrated
resource scale and stronger lifecycle verification. New speed, lower production
memory, a hardware ceiling, and full funding closure are not demonstrated by
this continuation. Recommendation: MORE ENGINEERING REQUIRED for final closure.

## Evidence and reproduction

Canonical package:
`evidence/performance/v2/linux-b3-continuation-d0792699`.
Its `checksums.sha256` SHA-256 is
`0223ab996a421cbd9dce8d57ff30f1e1b9506276bd0733dac33e0c120a51d659`.
Use `before-analysis.json`, `after-analysis.json`, `summary.json`, and
`raw-evidence.json`; these bind source stages, raw roots and retained failures.

Endpoint CV is sample standard deviation divided by mean times 100, using each
role's last `cycle_medians` private-resident value from the three complete runs.
Combined slopes above sum the source and destination
`derived_active_private_resident_slope_bytes_per_unit` within each source stage.
This review adds no benchmark runs and changes no accepted raw artifacts.
