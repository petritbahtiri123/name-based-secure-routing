# Task 4h — external-only burst diagnosis

**PASS / BURST-HARNESS-SCHEDULING-LIMITED.** This is a diagnostic result, not a
256-client capacity claim and not a production NBSR limit.

## Scope and provenance

Branch `codex/nbsr-v3-wp0-wp1`, capture base
`b8de2afca606f302719b60846abcf969730606d4`, Windows loopback, release binaries,
Intel i5-10210U (4 physical cores / 8 logical processors), 16,942,501,888 bytes
RAM. Exact commands, runtime versions, binary hashes, source hashes, timestamps,
and configuration are in `environment.json`. The batch gate is benchmark-only;
production, wire, security, authority, close behavior, and the existing
handshake/admission deadlines are unchanged.

All logical client tasks are created before the current-thread runtime can poll
them. When enabled, each task awaits an in-memory Tokio timer before constructing
its connection future; its existing handshake deadline therefore begins at its
actual connection attempt. Clients retain independent connections, sessions,
routes, ownership, outcomes, and cleanup. Disabled mode adds no release delay.

## Diagnostic result

Five valid repeats were collected for each 256-client cell. The release interval
was 25 ms; batches are diagnostic pacing only.

| Release | Median admitted | Success | Admissions/s | Established Gbit/s | Established p99 | Effective cores | Cleanup |
|---|---:|---:|---:|---:|---:|---:|---|
| Simultaneous | 216/256 | 84.38% | 40.742 | 0.700 | 3.252 s | 1.375 | CLEAN |
| Batch 8 | 256/256 | 100% | 138.068 | 0.660 | 0.646 s | 1.379 | CLEAN |
| Batch 16 | 256/256 | 100% | 94.516 | 0.642 | 1.134 s | 1.396 | CLEAN |
| Batch 32 | 256/256 | 100% | 96.224 | 0.700 | 1.166 s | 1.386 | CLEAN |

Every batched cell admitted 256/256 in every repeat. Simultaneous release had a
median of 216/256. Batch 32 improved admission success by 15.625 percentage
points while reaching 100%, satisfying the predeclared rule (at least 99% and at
least a 5-point improvement). The 128→256 collapse is therefore supported as a
simultaneous-burst / benchmark-scheduling limit under this harness and host.
The batched cells do not establish sustained 256-client capacity.

All cells released connection/session/channel/stream ownership to zero. No
deadline was lengthened and no lifecycle failure was converted to success.

## Packet-capture observer gate

Five alternating simultaneous OFF/capture pairs used Dumpcap/TShark 4.6.7 on
`\\Device\\NPF_Loopback`. Raw `.pcapng`, Dumpcap stderr, raw TShark tables, and
derived per-flow tables are preserved under `raw/simultaneous_capture/`.

The capture observer gate **FAILED**. Median changes included 15.78% established
goodput, 7.13% admissions/s, 23.05% established p95, and 22.95% established p99;
admission success shifted by 6.64 percentage points. These exceed the approved
5% / 1-point limits. Capture cleanup remained clean, but packet timings are not
usable for causal attribution. No batched packet captures were collected after
the failed gate. The preserved packet counts and flow tables are raw diagnostic
artifacts only; encrypted traffic is not used to claim QUIC-internal behavior.

## Reproduction

Run from the repository root with a fresh output directory:

```powershell
$env:CARGO_TARGET_DIR = 'C:\NBSR-build\b4b-task4h'
python -u scripts/run_b4b_task4h.py --output C:\NBSR-build\task4h-new-run --duration-seconds 20 --warmup-seconds 2 --release-interval-ms 25
```

`analysis.json` is derived programmatically from the raw records. The checksum
manifest covers the raw results, pcaps, flow tables, environment, and captured
source. Raw benchmark and packet evidence was not manually edited.

Final lint review removed one redundant local binding from `perf_rust_source.rs`;
the captured source and its hash remain preserved byte-for-byte. The binding
only copied an already `Copy` gate into the same `async move` closure, so its
removal does not alter the measured binary behavior or benchmark semantics.

## Claim boundary and next step

The result supports burst/harness scheduling limitation, not a Windows network,
QUIC-internal, production NBSR, hardware, or capacity ceiling. Packet-level stage
attribution remains unresolved because capture distorted the workload. The
smallest justified next step is to retain the diagnostic gate as an external
pacing control and redesign a lower-overhead external observer before claiming
where within an unpaced burst the delay occurs. No optimization, sharding, or
B3-v2 work follows this commit.
