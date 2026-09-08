# September 8 current-host B5 requalification

Source: `09a669a343330b381c67605114338cdc87d420e4`, release Linux binaries.
Their hashes match the preceding befccf5f build. This is Docker/WSL loopback,
not native server or WAN evidence. No production optimization was made.

## Preparation diagnostic

Six independent NBSR attempts compare 3-second versus 60-second unpaced
warmup, three attempts each in alternating order. The fixed historical offered
rate, 1 KiB payload, 32 streams, depth one, intended 120-second interval and
10-second progress cadence are unchanged. All six abort on the existing
destination private-resident growth guard. No assertion, timeout or resource
threshold was relaxed. Longer unpaced warmup does not resolve this paced
memory issue. The runs are diagnostic failures, not completed soaks or proof
of a leak, allocator cause, or a production bottleneck.

Raw: `C:/NBSR-build/linux-b5-preparation-09a669a3`.

## Fresh finite reference

Thirty valid paired Direct/NBSR records use 1 KiB, 32 streams, depths 1/2/4,
3-second warmup and 30-second timed intervals. Each cell has five repeats
because dispersion exceeded 5%. All six cells classify SATURATED under the
existing stability rules; all retain successful error/timeout/cleanup gates.

| Path | Depth | Median Gbit/s | CV | Classification |
| --- | ---: | ---: | ---: | --- |
| Direct | 1 | 0.906019 | 29.20% | SATURATED |
| Direct | 2 | 1.047467 | 11.73% | SATURATED |
| Direct | 4 | 1.278436 | 30.78% | SATURATED |
| NBSR | 1 | 0.985654 | 20.02% | SATURATED |
| NBSR | 2 | 1.214170 | 19.44% | SATURATED |
| NBSR | 4 | 1.492971 | 20.46% | SATURATED |

No strict-stable current-host calibration was obtained. Consequently no
qualified near-ceiling soak was launched using the older faster reference.
These results do not replace earlier measured stages with an NBSR capacity
claim: the changed host performance remains unattributed.

Raw: `C:/NBSR-build/linux-b5-reference-09a669a3`. Exact commands, every record,
the existing classifier output and source/build provenance are retained.
Two brief additional Windows power/load snapshots were taken during this
reference. They are disclosed diagnostic observers, not continuous thermal
telemetry or causal qualification. The five CPU samples span approximately
39-65% host utilization; neither these nor the WMI nominal clock prove a
hardware ceiling. Capture/profiler overhead has not been qualified.

## Decision

B5 remains INCONCLUSIVE / NOT_PROVEN for sustained near-ceiling capacity.
Retain the memory-growth failures and variable current reference. Continue
independent lifecycle/resource work. Before a funding-safe 60/120-minute soak,
establish a stable matched current-host reference and defensible memory and
observer attribution. The external runbook describes the executable subset;
native/server-class results remain unavailable.

Canonical evidence and retained raw-root checksum indexes:
`evidence/performance/v2/b5-host-requalification-09a669a3`.
