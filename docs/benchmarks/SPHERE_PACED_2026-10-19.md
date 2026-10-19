# SPHERE controlled-load result and paced warmup

A paced measurement previously left its three-second warmup unpaced. That could
trip an interface-bandwidth guard before measurement began. The benchmark sender
now applies the existing aggregate 10 ms pacing budget during NBSR warmup,
partitions it across streams, discards missed budgets and preserves response
validation. Warmup remains outside measurement accounting. Zero warmup is retained.
This changes benchmark code, not protocol/library security semantics.

The finite Python harness accepts explicit `--diagnostic-seconds 20` and `300`.
These profiles use one-second progress, with 60/330-second controller bounds;
historical default and 60/3600/7200-second profiles keep their existing cadence.
The existing single duration field reaches commands, both endpoints and offline
validation. No task-specific release-manifest pins replace the default validators.
`sphere_support/paced_contract.py` and `paced_progress.py` expose the tested pure
resource/deadline and grouped-progress checks for externally owned runners. Merely
importing them starts nothing; they do not automatically replace a legacy runner.

## Earlier 6000 operations/s evidence

See [sanitized summary](sphere-2026-10-19/controlled-6000-summary.json). One connection,
two streams, depth one, 1024-byte request and response, 3-second paced warmup,
6000 aggregate operations/s, one core-equivalent per VM:

| Measurement | Completed operations | Useful payload per direction | Errors/timeouts |
|---|---:|---:|---:|
| 20 seconds | 119998 | 49.1507 Mbit/s | 0 / 0 |
| 300 seconds | 1799914 | 49.1496 Mbit/s | 0 / 0 |

The 300-second run skipped 86 offered slots, rather than catching up. Interface
traffic peaked at 57.1872 Mbit/s; workload cgroup memory peaked at 38.3398 MiB.
There were no interface errors/drops. Owned cgroups, TLS holders/directories,
temporary mountpoints and local process groups were independently confirmed absent.
The unchanged guard stops after TX **or** RX exceeds 100 Mbit/s in two consecutive
one-second samples. It is an abort rule, not traffic shaping.

The two VMs shared a physical host and bridge. This is controlled-load completion,
not maximum capacity, WAN performance, or a laptop-loopback comparison.

## Earlier 6000 operations/s latency interpretation

Median steady-window p50/p95/p99 was 167.380/200.389/224.847 microseconds.
Every 64th completion is sampled: 93–94 observations per one-second window.
Nearest-rank p99 is therefore that window's largest sampled latency, not a pooled
p99 of all operations. The timer spans encode/write/read/validation and scheduling;
it excludes waiting for a pacing permit.

Six cumulative drift flags occurred at seconds 30, 31, 32, 33, 34 and 37. The rule
compares median window p99 in the first and last thirds observed so far and flags
a rise over 20%. Late medians ranged from 252.639 to 305.534 microseconds against
baselines of 207.199–210.440 microseconds. The full run's first/last 99-window
comparison was 224.509/227.438 microseconds (+1.30%). The largest sampled window
p99 was 2463.829 microseconds at second 117. Flags overlap; they are not independent
failures. No sampler overflow occurred, but these records cannot attribute delay
to network, VM scheduling, CPU quota or application processing.

## Provenance and checks

The measured sender was built from base `b09a85187d1e27250a1aec2e76f7a5bcdef84611`
plus the retained warmup patch; its binary and patch hashes are in the summary.
Runtime source was `47d2ae41df49fedd21768db5fa6be71377acebf3`. The integrated version
uses the driver's pacing module directly, adds Cargo-discoverable warmup tests and
preserves zero warmup. Do not attribute the retained 6000/s live result to a later
integrated binary without separately testing it. Raw evidence stays local;
selected raw hashes permit comparison without publishing credentials or host data.

Focused tests: `tests/performance/test_sphere_paced_regression.py`, native
paced/duration/peer/pair, finite run/endpoint and debug-correctness neighbors.
The offline support aggregate is
`python scripts/performance/sphere_support/run_offline_tests.py`.
Warmup regressions are under `perf_rust_source::paced_warmup_tests`; use the
provisioned offline build environment and existing build/resource supervision.
Cargo formatting and scoped Ruff checks are also required. None of these commands
authorizes a live workload or larger limits.

The realized NIC `EQ 100000000` resource constraint is distinct from the harness
guard and model link emulation. The inspected model requested no link emulator.
Enforcement/entitlement is unresolved; physical NIC speed establishes neither.
Any later rate trial or limit change requires explicit authorization and a fresh
bounded run with correctness and ownership-cleanup gates.

## Completed 8000 operations/s follow-up

After publication of signed commit
`4a2d93f881a62c326416e1379579c99663c70c59` and successful completion of all seven
Project checks jobs, one 20-second smoke and one 300-second trial completed at
8000 aggregate operations/s. The connection/stream/depth/payload shape and all
resource, bandwidth, TLS and cleanup guards above remained unchanged.
See the [8000 operations/s summary](sphere-2026-10-19/controlled-8000-summary.json).

| Measurement | Scheduled operations | Completed | Missed slots | Useful payload per direction | Errors/timeouts |
|---|---:|---:|---:|---:|---:|
| 20 seconds | 160000 | 159886 | 114 | 65.4885 Mbit/s | 0 / 0 |
| 300 seconds | 2400000 | 2397718 | 2282 | 65.4736 Mbit/s | 0 / 0 |

Missed slots were skipped, not recovered through catch-up bursts. The long run
completed 99.9049% of scheduled operations. Its peak sampled interface traffic
was 76.4167 Mbit/s, distinct from useful payload goodput; peak workload cgroup
memory was 38.1484 MiB. There were no interface drops/errors or sampler overflows.
Both runs passed independent owned-process, cgroup, ephemeral TLS and temporary
mountpoint cleanup checks; local workers exited with no owned handles.

The long run's median steady-window p50/p95/p99 was
164.390/196.338/212.049 microseconds. Neither follow-up run detected drift under
the existing rule. The every-64th-completion sampling and window aggregation
caveats still apply: these are not pooled percentiles and do not establish
stable latency beyond this methodology or run. The same-host VM topology remains;
these measurements establish neither maximum capacity nor WAN performance.

The follow-up used the rebuilt sender whose complete inventoried crate source
matched publication commit `4a2d93f881a62c326416e1379579c99663c70c59`:
SHA-256 `8b04e0a77c4c5c1d40f2d0559c73477c25197f8744a96af0a898cbce42424def`.
It differs from the earlier 6000/s sender. The unchanged server hash remains
`3f1ae36f1986eb1b94d085d5c457670d9219649d25ab07bd4369ea03624616cd`;
runtime checkout remains `47d2ae41df49fedd21768db5fa6be71377acebf3` with the
reviewed task-local runner overlays. The runner used its explicit
`--benchmark-seconds` contract; it did not replace the remote runtime checkout
with the publication checkout or claim end-to-end testing of every published
harness path. Source equivalence, release hashes, raw evidence hashes and cleanup
were checked separately. Raw logs, binaries, private role material and host
identifiers remain outside this publication.

## Completion and remaining work

Completed: paced warmup fix and regressions; signed source publication and CI;
separate 6000/s and 8000/s smoke/five-minute measurements; bounded resource and
integrity validation; verified cleanup and sanitized evidence. No workload remains
from these runs, and no further test is scheduled by this document.

Still pending: authoritative NIC allocation/enforcement semantics; a separately
authorized controlled capacity sweep; and a fair laptop comparison using matched
workloads, resource constraints and measurement methods. The current runs do not
complete those tasks or authorize higher limits, more cells or topology changes.
