# NBSR technical evidence: working brief

**DRAFT — NOT a final funding freeze.** This is a navigation and claims brief
for the ongoing campaign. Each measurement belongs to its recorded source,
workload and host; different stages are not one final-SHA scoreboard.

NBSR is being evaluated as a secure route to an isolated private origin. The
accepted PoC connects a client through non-frozen ISP adapters, the unchanged
NBSR secure path, and a fixed Origin Connector. Authority, authentication,
authorization, proof of possession, replay protection and admission precede
application payload. Benchmark improvements do not authorize weaker checks.

```mermaid
flowchart LR
 C[Client] --> A[ISP-A adapter]
 A --> N[NBSR secure path]
 N --> B[ISP-B adapter]
 B --> O[Origin Connector]
 O --> P[Isolated private origin]
```

## September9 closure caveat

The full quality checkpoint finds a pre-existing independent federation package
trust-anchor mismatch. Its current-package test fails closed; do not claim all
current conformance checks are green. See [the authority blocker](FEDERATION_PACKAGE_AUTHORITY_BLOCK.md).
Rust384 tests pass; four Go module race suites and all five vet runs pass.
The six five-minute preparation diagnostics still do not qualify a sustained soak.
See [the budget checkpoint](ENGINEERING_CHECKPOINT_2026-09-09.md).

## Latest September8 resource follow-up

MEASURED at0124f8ad:2048 active materialized bundles pass five repetitions each
with two and four allocated Linux guest CPUs, with clean final ownership.
Combined role-median private-resident totals are1,404,301,312 and1,408,299,008bytes;
these include both endpoint processes and transport/runtime/fixture costs.
The first4096 attempt fails. All six one-CPU buffer diagnostic attempts fail;
no Linux production buffer optimization or hardware ceiling is justified.
[Resource evidence](../../evidence/performance/v2/linux-resource-scale-0124f8ad/REPORT.md).

The repaired Linux finite admission ladder at2a30272e has23 valid records:
125 offered/s ->119.313320 actual/s STABLE;150 ->142.418287 DEGRADED;
200 ->111.350407 SATURATED. This is mixed-workload VM evidence, not sustained
production capacity. [Admission evidence](../../evidence/performance/v2/linux-followup-2a30272e/REPORT.md).
The short paced preflights still fail; a qualified60/120-minute soak remains
NOT_PROVEN. Earlier scoreboard rows below retain their source/workload scope.

## Evidence available now

| Area | Defensible statement | Qualification / source |
| --- | --- | --- |
| Single physical core | MEASURED 0.865859 Gbit/s and 52,847.849 ops/s at 1 KiB/64; 1.052536 Gbit/s and 4,015.106 ops/s at 16 KiB/8; both depth 1 strict-stable | Windows loopback, both roles share one physical-core allocation, cbdca987; [calibration](../../evidence/performance/v2/physical-core-calibration-cbdca987/REPORT.md) |
| CPU efficiency | DERIVED 18,601.695 and 242,551.717 CPU ns/op for those respective shapes | Sampled process CPU, both roles; not isolated protocol instruction cost or exclusive OS core isolation |
| Four-core forwarding | MEASURED 2.306118 Gbit/s strict-stable in its recorded 4-group/16KiB/1-stream stage | Five repeats; other shapes/stages have separate latency baselines; [multicore](../../evidence/performance/v2/physical-core-multicore-53468db4/REPORT.md) |
| Admission | MEASURED highest tested stable offered rate 125/s gives119.920 actual/s; 150/s DEGRADED; 200/s SATURATED by achieved/offered ratio | Finite 512-client batches with two source shards, not sustained admissions/s/core or a production ceiling; [admission](../../evidence/performance/v2/admission-fresh-1917b195/REPORT.md) |
| Resource scale | MEASURED 35 valid cells through 2,048 materialized streams on 32 fixed channels; all 11 final ownership counters zero on both roles | Fixture residency scale, not a global resource/hardware ceiling; [memory](../../evidence/performance/v2/b3-wide-streams-b29054b9/REPORT.md) |
| Resource cost | DERIVED about 40,473 additional combined process-private bytes per held stream in that fixed 32-channel series | Includes QUIC/runtime/allocator/fixture costs; not pure NBSR object size; retained-memory cause remains INCONCLUSIVE |
| Sustained stability | NOT_PROVEN near the new ceilings | At 2d7525f3, one NBSR 10-minute run achieved 0.555331 Gbit/s, 97.68% of offered load, zero errors/timeouts and eleven-counter cleanup on both roles. Repeat 2 aborted on source-private growth; Direct's separate 10-minute run achieved only 20.17% of offered load. No qualified 60/120-minute soak; [qualification](../../evidence/performance/v2/b5-qualification-2d7525f3/REPORT.md) |
| Wire accounting | MEASURED 20 matched captures with zero reported capture loss; setup UDP-payload increment is consistent; whole/established deltas cross zero | No constant data-overhead, physical Ethernet, or phase-aligned L2 claim; [packet accounting](../../evidence/performance/v2/b1-packets-e2c75b59/REPORT.md) |
| Adversarial checks | MEASURED 13 fail-closed executable cases pass at their recorded source | Replay, tampering, bindings, expiry/revocation/generation, downgrade, unauthorized/forged identity, malformed input and failure/recovery; refresh at bf53b8d4:13 PASS/0 FAIL/1 network-isolation INCONCLUSIVE; final whole-campaign gates remain pending; [refresh matrix](../../evidence/security/adversarial-refresh-bf53b8d4/summary.md) |
| Private origin | MEASURED three Docker network lifecycles deny client/ISP-A DNS/IP direct probes, then return the exact authorized body with one origin request | Local topology, shared test bootstrap material, no host/root resistance claim; [isolation](../../evidence/security/isp-isolation-f831c9bb/REPORT.md) |
| Federation | MEASURED admission preflight separately from route isolation; live runtime federation NOT_PROVEN | No independent-operator live-federation claim |
| Linux | MEASURED at 8779e69c: NBSR finite depth-one 1.822417 Gbit/s STABLE, depth-two 2.165110 DEGRADED, depth-four 2.432145 SATURATED | 22 valid rows; one selected guest-core representative, 1 KiB/32 streams. Direct baseline remains dispersed. Docker Desktop VM, not dedicated physical-server/NIC evidence; [reference](../../evidence/performance/v2/linux-reference-8779e69c/REPORT.md). Paced memory/soak qualification remains pending. |

## Why the numbers changed

Early forwarding was limited by timed benchmark SHA framing and single-runtime
endpoint scheduling. The campaign removed those measured harness artifacts,
then separated verified physical cores, queue depth and endpoint groups. This
is benchmark-interference removal, not evidence of a production speedup.
Mandatory protocol cryptographic verification was not sampled or skipped.

Admission harness repairs addressed process/listener fanout, synchronous
lifecycle polling, unread stderr, simultaneous launch and source-runtime
pressure. A bounded Windows UDP receive-buffer change was justified by captured
insufficient-buffer drops and applied symmetrically to Direct. Residual handshake
attribution remains PLATFORM_DIAGNOSTIC_LIMIT because the tested observers failed
distortion gates; no production capacity claim follows from that limit.

## Claims suitable for a technical discussion

- The project has reproducible local performance, cleanup, adversarial and
  network-isolation evidence with raw artifact hashes and explicit failure cases.
- Finite single-core workloads can saturate the allocated core while preserving
  the tested security/admission behavior. Exact workload/source figures above
  may be quoted with their Windows-loopback scope.
- The isolated-origin PoC and federation admission preflight are demonstrated
  separately. They do not establish live runtime federation.
- Server-class, WAN and near-new-ceiling sustained validation remain engineering
  gates; an external partner would help execute those measured comparisons.

Do not claim production/ISP capacity, a server hardware ceiling, universal
per-connection memory cost, zero NBSR overhead, leak-free untracked allocations,
120-minute near-ceiling stability, or live independent-operator federation.
Do not use the 3.666 Gbit/s diagnostic peak or historical 2.942 Gbit/s degraded
result as strict-stable throughput. Historical 2.185 Gbit/s remains a separate
accepted stage, not a replacement for shape-bound current calibration.

## What remains before final outreach/funding packaging

Execute the authored native external runbook when hardware is available, finish
portable matrix preparation and final focused security/quality gates;
qualify or explicitly classify pacing/observer drift; complete source-compatible
soak/scaling work where valid; reconcile same-process private retention; freeze
the final commit, command and checksum index. External hardware is unavailable.
Linux sustained orchestration and its CLI are implemented, but current Rust
reference/soak qualification remains incomplete. The native external runbook
must retain its tested source binding; local Docker results do not validate a
server. One Administrator-only Windows Direct CPU attribution command is
deferred in the [Administrator ledger](ADMIN_REQUIRED_FINAL_VALIDATION.md).
Windows source-private growth remains open.

The finite Linux FD exit-transition handling is now regression-tested; the
original missing-context failure still cannot be attributed retrospectively.
At857b4080, preparing bounded benchmark latency storage removed its lazy-page
mechanism. The fixed-rate Linux rerun still failed destination-private growth
at100seconds. Subsequent mapping/allocator traces remain diagnostic and do not
qualify performance or a60minute soak. Windows started-descendant cancellation
now passes five repeats; the separate100ms deadline's descendant-start proof
remains INCONCLUSIVE. These updates do not raise the capacity claims above.

## September 8 continuation (not a final freeze)

At `40b277fb`, a separately named materialized `live-bundles` workload completed
five repeats at 512 and five at 1024 authenticated bundles, with eleven-counter
zero ownership on both roles and process exit. Standard QUIC keepalive is
explicitly enabled only for this benchmark scenario. Ordinary idle expiry,
negotiated idle limits and production defaults are unchanged. The old idle
1024 failures remain failures; three matched materialized idle controls now
retain 2,221 source failures with complete idle-expiry diagnostics.
Five 100-cycle repetitions completed 500 clean cycles with zero FD/thread
growth; the residual private-memory trend still does not prove an allocator
cause or a general plateau. See `B3_LIVE_BUNDLES.md` and its canonical package.

This is Docker/WSL loopback on one selected guest CPU with two source scheduler
shards, not proof of pinned host physical-core or server-class capacity. Active
hold scale is separate from sustained admissions/s and forwarding throughput.

The fresh `09a669a3` 1 KiB/32-stream paired reference has 30 valid records but no
strict-stable cell; six preparation diagnostics still abort on destination
private-resident growth. No new qualified soak or improved throughput claim
follows. See `B5_CURRENT_HOST_REQUALIFICATION.md`. Earlier finite figures retain
their original source, workload and host-state scope.

A later 40b277fb 16 KiB/eight-stream Linux finite reference classifies STABLE
at3.235685 Gbit/s; its separate 70% paced preflight fails p99 drift at150seconds.
This is observed Docker/WSL short-run evidence, not sustained/server capacity.
Windows07096c08 reproduces1.050835 Gbit/s STABLE for the one-physical-core
16KiB/eight-stream finite shape, but its short paced preflight also fails.
The2048 live-bundle attempt fails handshake progress;1024 remains the largest
accepted active-bundle count. See LINUX_SEPTEMBER8_REQUALIFICATION.md and
B5_WINDOWS_REQUALIFICATION_07096C08.md. A B4-only Linux exiting-process observer
repair is regression-tested; its post-fix admission rerun remains in progress.

Current campaign recommendation: **MORE ENGINEERING REQUIRED**. This brief is
not a readiness endorsement and must be rewritten around the final accepted
state before a funding evidence freeze.
