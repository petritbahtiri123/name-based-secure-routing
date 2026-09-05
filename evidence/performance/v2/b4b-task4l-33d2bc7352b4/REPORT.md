# Task 4l: matched two-shard handshake boundary profiling

**PARTIAL / UNRESOLVED:transport-handshake-progress. Administrator ETW capture pending.**

## Measured diagnostic result

Release source base `33d2bc7352b437d29398bd37e2ed1b54f35c0e6f`, Windows loopback,
two source shards, 512 independent client lifecycles, one connection per client,
30-second established window, two-second warmup. All deadlines, admission,
authentication, payload, ACK, and cleanup semantics are unchanged. No production
optimization was made. These are diagnostics, not new stable-capacity results.

Each rate used five alternating unprofiled/capture repeats after the three-repeat
CV gate required extension. All 20 records were valid; all owned resources
returned to zero and processes exited. Two bad-but-valid client task failures
are retained: client 141 in 200/s capture repeat 4 and client 262 in 250/s
unprofiled repeat 1. Both report `client_task_failed`, `timed_out=false`;
the lower-level cause is not recorded. No timeout or cleanup failure was reported.

| Offered/s | Observer | Repeats | Actual admissions/s | Handshake p99 ms | Established Gbit/s | Failed admissions |
|---:|---|---:|---:|---:|---:|---:|
| 200 | None | 5 | 142.832 | 1003.166 | 0.601370 | 0 |
| 200 | Npcap | 5 | 122.811 | 1010.133 | 0.516983 | 1 |
| 250 | None | 5 | 62.565 | 1044.534 | 0.624637 | 1 |
| 250 | Npcap | 5 | 42.815 | 3017.865 | 0.510547 | 0 |

Values are medians across repeats; failures are sums. Unprofiled 200/s actual
rates ranged approximately 56–175/s. This variability and the 250/s collapse
reproduce unresolved progression problems, not a named host or production bound.

## Observer rejection

Both existing absolute 5% observer gates failed. Admission-rate median differences
were 14.02% at 200/s and 31.57% at 250/s; established goodput differences were
14.03% and 18.27%. At 250/s handshake p99 differed by 188.92%.
Host/run variation is confounded with observer effects: these percentages do not
isolate intrinsic capture cost. Packet timings cannot attribute the unprofiled
stall. No claim of packet loss, Quinn retransmission/timer causality, source
runtime starvation, or Windows network saturation is made.

All ten Dumpcap logs report zero dropped packets. Dumpcap/TShark version 4.6.7
used `NPF_Loopback`, filtered to each dynamically bound admission listener UDP
port. TShark exports and pcaps remain raw diagnostics. No physical L2 measurement
or generic framing-as-NBSR-overhead claim is made. Capture startup includes the
existing 350-ms readiness delay after destination readiness; its effect is part
of the rejected observer comparison. UDP flow ports are not invented client IDs.

## Provenance and evidence

Raw immutable evidence (155,709,550 bytes across 232 files at preservation time):
`C:\NBSR-build\b4b-task4l-packet-33d2bc7352b4`.
`external-trace-manifest.json` indexes every external artifact by relative path,
size, and SHA-256; `external-checksums.sha256` is the original runner manifest.
All original checksums were freshly verified. `analysis.json` retains every
full repeat and observer calculation; `derived-summary.json` contains medians
and independently checked per-capture drop counts. Raw files were not edited.

The source executable hash differs from Task 4k; the current Rust source adds
`#[cfg(feature = "benchmark-harness")]` around the shard module, which remains
enabled in these release builds. Source snapshots and exact binary hashes are
recorded; the historical campaign is not merged into this result. The final
Python runner adds post-capture failure persistence and ETW comparison checks;
the exact earlier runner used for this packet campaign remains in external
`capture-source/`. Neither review correction changes this campaign's stored data.

## Historical claim correction for final packaging

Task 4k's two-shard 125/s baseline achieved 94.9139%, below the required 95%.
Its `BASELINE` label is not proof of strict stability. Retain the separate Task 4i
119.813 actual/s result only within that campaign's tested cell and limitations.
Task 4k reports and raw evidence remain unchanged. No new baseline or capacity
claim is introduced here.

## Next capture

The current token is Windows medium integrity with Administrator membership
disabled for elevation. The new wrapper exits `MANUAL_ELEVATION_REQUIRED` before
creating output. Installed xperf advertises scheduler, network, and timer events.
Kernel scheduling/network/timer ETW requires an Administrator process.

Run in Administrator PowerShell:

```powershell
pwsh -NoProfile -ExecutionPolicy Bypass -File "C:\Users\bajra\OneDrive\Documents\NBSR\scripts\capture_b4b_task4l.ps1"
```

The wrapper creates a fresh timestamped external directory, runs five controls
and five traced repeats per rate, verifies source/binary/workload equivalence,
saves observer gates and trace loss metadata, and prints `CAPTURE_READY` with the
path. It uses sampled profile stacks plus CSwitch/ReadyThread, network and timer
events; it avoids expensive stack capture on every context switch. Controls
precede the ETW block, an explicit temporal-drift confound. A passing observer
gate alone does not prove causality: zero loss and correlated event analysis
remain required. Failed gates withhold transferred timing/causal claims.

Packet reproduction uses a fresh output directory:

```powershell
python -u scripts/run_b4b_task4l.py --output C:\NBSR-build\task4l-fresh --mode paired
```

## Verification

- Initial RED: missing runner module; GREEN: 18 focused tests passed.
- Review RED: failed-repeat persistence and binary-mismatch tests both failed;
  GREEN: 20 focused tests passed.
- Ruff: PASS for the new runner and tests.
- PowerShell non-elevated preflight: expected `MANUAL_ELEVATION_REQUIRED`;
  elevated capture has not been run or claimed tested.
- Dependency and repository privacy checks: PASS (101 scoped files).
- External raw integrity: PASS; 20 valid records, 10 zero-drop capture logs.
- One focused independent review and one scoped re-review: no remaining
  Important/Critical finding after corrections.
- Rust/Go tests, fmt, Clippy and vet are not relevant to this orchestration-only
  stage; no Rust/Go/dependency/protocol file changed. Release binaries were built
  before measurement. Whole-program closure checks remain outstanding.

B3-v2, near-ceiling soak, B1-v2, external validation definition, ISP/Federation,
and funding package remain pending behind handshake attribution. Recommendation:
**MORE CLOSURE REQUIRED**.
