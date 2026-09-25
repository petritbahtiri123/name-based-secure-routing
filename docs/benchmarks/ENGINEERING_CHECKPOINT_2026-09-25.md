# NBSR engineering and evidence checkpoint — 25 September 2026

Start: `490dfad8d15c3b869d5b46f850f6ad59f0d6e47f` on
`codex/nbsr-v3-wp0-wp1`. This is a conservative evidence snapshot, not full
mission completion or a final funding freeze. No push, main integration,
production transport optimization or frozen security/wire change was made.
Main and origin/main remain `1938154d498b32d81a3564319969430644e8a688`.

## What this continuation changed

| Stage | Result and evidence |
| --- | --- |
| Linux exit observation | `8e0b28a2`: an independently verified owned-process exit can have unavailable memory. Preserve null instead of inventing zero or rejecting normal exit; live permission/identity failures still reject. |
| Native 2048 resource trial | Three of three pass: 6144/6144 authenticated connections and round trips, six owned PIDs absent, both final eleven-counter reports zero. [Evidence](../../evidence/performance/v2/native-live2048-memory2-8e0b28a2/summary.md). |
| Native 4096 boundary | `530ecac9` bounds collection for the larger workload. Three of three attempts fail before common active hold: 2031/3605/2500 materializations, no completed round trips. Destination UDP drops measured; no proven sole cause or hardware/production ceiling. [Evidence](../../evidence/performance/v2/native-live4096-530ecac9/summary.md). |
| Windows process cleanup | `ce67f206`: owned Job Object membership replaces insufficient parent/PID ancestry as cleanup authority. Regression first reproduced a surviving child. Termination, assignment and verification errors remain failures. |
| Cancellation fixture | `dfc22f2c`: the test waits for the existing asynchronous authority cleanup using its existing bounded helper. Production cancellation and deadlines unchanged. |
| Go lifecycle ordering | `97e0ca06`: an explicit local benchmark barrier waits for destination send completion before Go peer close. Baseline 17/18 versus corrected 18/18 cells; all 150 repeated cycles pass, 1680/1680 total round trips. [Before/after evidence](../../evidence/performance/v2/go-b3-completion-97e0ca06/summary.md). |
| Go/Linux measurement path | `4843c751` adds explicit Go selection and separate analysis, preserving narrower eight-counter destination ownership and unavailable final source memory. `d88663af` supplies the previously missing Linux monotonic benchmark clock. Thirty of thirty Linux cells pass: 16,800 round trips, including five repeats of fifty same-process cycles. Destination eight-counter cleanup and process exits verified; source ownership remains unmeasured. See the [Linux evidence](../../evidence/performance/v2/go-linux-lifecycle-de50692f/summary.md). |
| Windows duration arithmetic | `a9048589`: full-width QPC conversion removes measured signed overflow in long benchmark intervals. Synthetic two-hour regression and Go race/vet pass; this is not a two-hour soak. |
| Linux sampling startup | `7255c9d6` tolerates vanished nonleader tasks. A later retained smaps failure exposed a separate launch/exec window; `de50692f` waits for the existing exclusive Go runtime file before first idle sampling. Four RED then GREEN regressions, 38 affected tests pass; no network deadline changes. |
| Storage | Lossless compression of 1061 indexed retained artifacts recovered 2,290,399,694 allocated bytes. Before/after content hashes match; no authoritative evidence was deleted. A second indexed batch of 39 files recovered another 86,357,917 bytes with unchanged hashes. |

Quality and cleanup evidence: [retained initial failures and focused repairs](../../evidence/performance/v2/quality-followup-dfc22f2c/summary.md).
Full Python follow-up: 1612 PASS, three SKIP. Isolated Rust release: 406 PASS,
two ignored, after retaining the original close-timeout failure. Release
Clippy with warnings denied and fmt pass. Client, interop, demo and ISP Go race
suites pass at their recorded stages; five vet runs pass. The independent
federation verifier still rejects the current package's trust-manifest digest.
These are explicitly stage-bound results, not one all-green final-SHA suite.

Historical optimization context: timed benchmark SHA framing, endpoint scheduling,
process/listener fanout, synchronous lifecycle polling, unread stderr and burst
launch/source-runtime pressure were addressed in earlier harness stages. They
must not be marketed as production cryptographic work removed. The earlier
[bounded Windows receive-buffer change](../../evidence/performance/v2/b4b-task4m-217df28e/REPORT.md)
is a production implementation change: measured insufficient-buffer drops
justified a1MiB request, applied symmetrically to Direct/NBSR Windows listeners.
Its250/s p99 improved in five pairs, while p50 worsened and rate dispersion
remained high. The [later attribution report](../../evidence/performance/v2/b4b-task4n-aede59ac04e3/REPORT.md)
retains accepted scoped no-drop evidence and rejects the accept-pump observer;
it does not establish a general production speedup or host ceiling.

## Benchmark scoreboard and claim boundaries

Each row belongs to its stated source, shape and environment. Do not combine
historical maxima into a claim about one final binary or production capacity.

| Metric | Observed result | Scope |
| --- | --- | --- |
| One physical core, 16 KiB/eight streams/depth one | 1.052536 Gbit/s; 4015.106 ops/s; p99 3.7861 ms; 0.967658 effective cores | MEASURED at cbdca987, Windows loopback; 242551.717 CPU ns/op DERIVED |
| One core, 1 KiB/64 streams/depth one | 0.865859 Gbit/s; 52847.849 ops/s; p99 2.4867 ms; 0.982960 effective cores | MEASURED at cbdca987; 18601.695 CPU ns/op DERIVED |
| Same one-core 16 KiB ladder | 1.157283 degraded at depth two; 1.133049 saturated at depth four | Keep latency and workload qualification |
| Four selected physical cores | 2.306118 Gbit/s strict-stable, five repeats, CV 0.908%, p99 1.085 ms | MEASURED at 53468db4, 16 KiB/one stream per group/four groups |
| Four-core saturated ladder | 2.643019 / 2.976737 / 3.218905 / 3.361954 Gbit/s at depths 2/4/8/16 | SATURATED; individual 3.666140 peak is DIAGNOSTIC |
| Older maximum-throughput stage | 2.185 strict-stable / 2.942 repeatable degraded / 3.040 observed saturated peak Gbit/s | HISTORICAL, separate workload; not superseded by silently pooling stages |
| Finite Windows admission | 125 offered/s → 119.920 actual/s stable; 150 → 138.887 degraded; 200 → 176.182 saturated | MEASURED at 1917b195, 512-request cells, not indefinitely sustainable capacity |
| Admission latency at 125 | Handshake p99 10.110 ms; admission p99 28.327 ms | Same finite workload; 27 valid ladder rows, 13824 admissions, zero errors/timeouts |
| Largest accepted native live count | 2048, three new repeats | Local namespaces; 100 offered/s, keepalive enabled; functional/resource scale, not stable admission |
| Native 2048 memory | Source 806.908203 MiB; destination 546.267578 MiB active private resident | MEASURED medians; multiple resource axes co-vary; not isolated bytes/connection |
| Repeated lifecycle | Native 3 × 50 cycles; corrected Windows Go 3 × 50 cycles pass | Owned cleanup measured within each implementation's stated counter coverage |
| Long-run near-ceiling stability | NOT_PROVEN | No qualified uninterrupted 60/120-minute B5 acceptance |
| Packet accounting | Additional setup IP bytes: median 38590 at 1 KiB/64 streams, 15596 at 16 KiB/eight streams | MEASURED at 6b1095c5, twenty matched capture cells; setup differs from established traffic |

Sources: [single core](../../evidence/performance/v2/physical-core-calibration-cbdca987/REPORT.md),
[four cores](../../evidence/performance/v2/physical-core-multicore-53468db4/REPORT.md),
[finite admission](../../evidence/performance/v2/admission-fresh-1917b195/REPORT.md).
Two-core throughput and the matched four-core Direct control remain dispersed;
linear scaling or a Direct-relative speedup is unsupported. Allocations/op,
syscalls and context switches have not been established for these cells.
Retained memory alone is not a leak or allocator attribution. Established packet
deltas are small and signed; generic QUIC/UDP/IP framing is not an NBSR tax.
Physical L2 estimates are derived, not physical-wire measurements.

## Security and ISP/federation

The [accepted adversarial refresh](../../evidence/security/adversarial-refresh-bf53b8d4/summary.md)
has 13 PASS, zero FAIL and one direct-origin INCONCLUSIVE at its own SHA.
Replay, tampering, service/port/transport/PoP binding, expiry, revocation,
generation, downgrade, unauthorized source, malformed input, forged identity
and failure/recovery retain their original scenario scope.

Separately, [Docker private-origin isolation](../../evidence/security/isp-isolation-f831c9bb/REPORT.md)
passes three fresh lifecycles: all twelve client/ISP-A DNS/private-IP probes
fail to reach the private origin; the authorized secure route returns the exact
body once; teardown leaves no owned containers, networks or volumes. This is
genuine isolated-network evidence, not a retrospective PASS for a different SHA.

The approved architecture remains Client → non-frozen ISP-A adapter → unchanged
NBSR secure path → non-frozen ISP-B adapter → Origin Connector → isolated origin.
Federation admission preflight has its separate fixture evidence. **Live runtime
federation is NOT_PROVEN.** Changing the frozen trust manifest to make the current
package verifier pass is not authorized as a performance fix.

## Remaining work — explicit, not a percentage estimate

| Classification | Item and next prerequisite |
| --- | --- |
| COMPLETE | Scoped native 2048 resource evidence; 4096 failure preservation; owned Windows child cleanup; corrected Go lifecycle ordering and Windows repeats; indexed quality/storage evidence |
| PLATFORM_DIAGNOSTIC_LIMIT | Handshake attribution and timing qualification: rejected ETW/AFD and native observer cohorts cannot identify a sole production cause. No further blind instrumentation escalation justified. |
| ADMIN_REQUIRED | One prepared Windows Direct paced CPU comparison; exact command, question and output gates in [the administrator ledger](ADMIN_REQUIRED_FINAL_VALIDATION.md) |
| EXTERNAL_HARDWARE_REQUIRED | Actual dedicated Linux/server, physical NIC, WAN/NUMA/core scaling and less-distorted reference/observer qualification |
| BLOCKED_ARCHITECTURAL | Independent live federation current-package/frozen trust-manifest mismatch; preserve fail-closed verification |
| BLOCKED_DESTRUCTIVE | None required; no destructive action used to advance results |
| PARTIAL | Full portable external matrix, Go source resource ownership and isolated marginal resource costs; Linux loopback is only a subset |
| NOT_PROVEN | Qualified near-ceiling 60/120-minute soak; requires a qualified current reference and observer first |
| OPTIONAL_LOW_VALUE | Repeating the same noisy Windows/native diagnostics without a new causal question |

Do not start a long soak merely to produce elapsed hours while its reference or
observer fails acceptance. Do not claim an idle-CPU plateau is a hardware ceiling.
The [external validation definition](EXTERNAL_LINUX_SERVER_VALIDATION.md) retains
exact build/workload/telemetry requirements and clearly labels incomplete ports.

## Outreach wording

Safe: “NBSR has reproducible local authenticated transport, adversarial and
private-origin isolation evidence. A scoped four-core Windows loopback workload
measured 2.306 Gbit/s strict-stable throughput. Separate local trials completed
2048 concurrent live connections with verified cleanup. Server capacity,
sustained near-ceiling stability and live federation remain under validation.”

Unsupported: production/ISP/WAN capacity; 3.666 Gbit/s stable; burst or finite
admissions as sustainable capacity; universal no-leak/no-race guarantees; linear
scaling; independent production federation; a fully complete funding-grade package.

Recommendation: **READY FOR TECHNICAL OUTREACH**, with these limitations attached.
**MORE CLOSURE REQUIRED** for pilot readiness or a final performance-backed funding
freeze. Funding conversations may describe the research and measured progress;
they must not imply that the remaining acceptance gates passed.

## Evidence inventory and reproduction

Consult each linked package's report and checksum index. New September25 packages
use `raw-evidence.json` to pin local raw roots and their index hashes; older
packages may use `analysis.json`, `raw-checksums.sha256` or `external-inputs.json`
instead. Raw roots are under `C:/NBSR-build` and are not automatically included
in a Git clone. Transfer canonical and raw artifacts using the package-specific
index, then verify every indexed digest before replay.
No claim of off-host backup or public evidence publication is made.

Native 2048 canonical index SHA-256:
`ce943b5a465643ab21ca5cc03c794522fdab501dceaa393163b6b7b0854ef56f`.
Native 4096 canonical index SHA-256:
`4517c6aa9851569e034a319707123e16265b2813272c93b6e8b28703270d4bf8`.
The Go completion package's `analyze.py` reconstructs the baseline/corrected
comparison from retained raw cells; quality and native packages provide their
own exact commands and source/binary bindings. No unfavorable valid run is removed.

## Commit sequence in this continuation

The final Go/Linux stream ladder passes another 30/30 cells: five repeats each
at 64/128/256/512/1024/2048 streams across 32 fixed channels in one connection.
All 20,160 round trips complete with eight destination counters zero and both
processes exited. This is separate from the native 2048-connection result.
At 2048 streams, active private-resident medians are 20,144,128 source bytes and
5,885,952 destination bytes. Source/destination repeat CVs are 0.346%/0.456%.
These are measured process footprints, not isolated bytes/stream or a maximum.
The Linux package verifies six canonical artifacts, seven privacy-scanned files
and 967 indexed raw artifacts, including failed attempts and source bindings.
No campaign container remains running after the final ladder.

```text
8e0b28a2 perf: preserve unavailable memory during verified owned exit
530ecac9 perf: bound native 4096 live source evidence collection
be07f67c evidence: verify three native 2048 memory trials after exit fix
46c3e289 test: align feature and cancellation fixtures with current harness contracts
169ccf63 evidence: retain three native 4096 failures without capacity claims
ce67f206 fix: verify Windows durable benchmark cleanup with owned jobs
dfc22f2c test: await authority worker cleanup in assembled cancellation fixture
a2962463 evidence: retain quality failures, focused repairs and lossless storage savings
97e0ca06 perf: coordinate Go lifecycle close after destination send completion
63c619b6 evidence: verify Go lifecycle completion across 18 Windows cells
4843c751 perf: add scoped Go-to-Rust Linux lifecycle capture and validation
d88663af fix: provide monotonic Linux clock for Go benchmark peer
7255c9d6 fix: tolerate vanished Linux nonleader tasks during resource sampling
a9048589 fix: preserve long Windows benchmark intervals without tick overflow
de50692f perf: wait for Linux Go initialization before memory sampling
```

The following evidence/documentation commit seals this checkpoint; its SHA is available from Git history.
