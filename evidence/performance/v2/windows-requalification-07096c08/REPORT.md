# Windows current-source requalification at 07096c08

Release Windows loopback, one verified physical core, one endpoint group.
This is a new measured stage, not an improvement attributed to production code.

## Finite reference

16 KiB, eight streams, depths 1/2/4, three-second warmup and 30-second measurement.
22 valid rows: three repeats per path at depths one/two, five at depth four.

| Path | Depth | Median Gbit/s | Classification |
| --- | ---: | ---: | --- |
| Direct | 1 | 1.092551 | STABLE |
| Direct | 2 | 1.103974 | SATURATED |
| Direct | 4 | 1.101815 | SATURATED |
| NBSR | 1 | 1.050835 | STABLE |
| NBSR | 2 | 1.155600 | DEGRADED |
| NBSR | 4 | 1.108855 | SATURATED |

The NBSR depth-one median is approximately 4,008.6 operations/s, with sampled
CPU 242,435 ns/op and 0.971 effective cores. These finite metrics are not a
sustained paced-capacity claim. Raw: C:/NBSR-build/windows-reference-16k8-07096c08.

## Paced attempts retained

Six predeclared 120-second diagnostics used the unchanged historical fixed
rate 5206274500000/150044089 operations/s, 1 KiB, 32 streams, depth one.
They do not establish a current near-ceiling load.

- Direct repeat one completed at 0.115764 Gbit/s and 20.36% achieved/offered;
  repeats two and three failed the live goodput-drift guard.
- NBSR repeats completed at 0.554338, 0.539986 and 0.544313 Gbit/s, respectively
  97.510%, 94.985% and 95.746% achieved/offered. Diagnostic completion does not
  imply the strict 95% pacing gate passed in every repeat, or close the prior
  ten-minute memory-growth failure.

A separate reference-bound 70% 16 KiB/eight-stream 120-second preflight retained
repeat one at 0.703977 Gbit/s, 95.704% achieved/offered. Repeat two failed the
unchanged 95% gate at 0.697508 Gbit/s and 94.828%. The failed prefix was retained;
no third replacement or long soak was launched from this failed preflight.

Raw: C:/NBSR-build/windows-b5-requalification-07096c08. Build provenance:
C:/NBSR-build/windows-current-07096c08. No benchmark overlapped another benchmark
or a build. Observer qualification, thermal/power attribution and a qualified
60/120-minute soak remain NOT_PROVEN. Windows Direct pacing attribution remains
the existing deferred Administrator validation; these data do not justify a
production optimization, hardware ceiling, relaxed guard or changed workload.
