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

## Evidence available now

| Area | Defensible statement | Qualification / source |
| --- | --- | --- |
| Single physical core | MEASURED 0.865859 Gbit/s and 52,847.849 ops/s at 1 KiB/64; 1.052536 Gbit/s and 4,015.106 ops/s at 16 KiB/8; both depth 1 strict-stable | Windows loopback, both roles share one physical-core allocation, cbdca987; [calibration](../../evidence/performance/v2/physical-core-calibration-cbdca987/REPORT.md) |
| CPU efficiency | DERIVED 18,601.695 and 242,551.717 CPU ns/op for those respective shapes | Sampled process CPU, both roles; not isolated protocol instruction cost or exclusive OS core isolation |
| Four-core forwarding | MEASURED 2.306118 Gbit/s strict-stable in its recorded 4-group/16KiB/1-stream stage | Five repeats; other shapes/stages have separate latency baselines; [multicore](../../evidence/performance/v2/physical-core-multicore-53468db4/REPORT.md) |
| Admission | MEASURED highest tested stable offered rate 125/s gives119.920 actual/s; 150/s DEGRADED; 200/s SATURATED by achieved/offered ratio | Finite 512-client batches with two source shards, not sustained admissions/s/core or a production ceiling; [admission](../../evidence/performance/v2/admission-fresh-1917b195/REPORT.md) |
| Resource scale | MEASURED 35 valid cells through 2,048 materialized streams on 32 fixed channels; all 11 final ownership counters zero on both roles | Fixture residency scale, not a global resource/hardware ceiling; [memory](../../evidence/performance/v2/b3-wide-streams-b29054b9/REPORT.md) |
| Resource cost | DERIVED about 40,473 additional combined process-private bytes per held stream in that fixed 32-channel series | Includes QUIC/runtime/allocator/fixture costs; not pure NBSR object size; retained-memory cause remains INCONCLUSIVE |
| Sustained stability | NOT_PROVEN near the new ceilings | Three light-load 120-second controls passed; subsequent 70%-load one-core observer cohort aborted on drift. No accepted new 60/120-minute soak; [retained abort](../../evidence/performance/v2/b5-observer-drift-cbdca987/REPORT.md) |
| Wire accounting | MEASURED 20 matched captures with zero reported capture loss; setup UDP-payload increment is consistent; whole/established deltas cross zero | No constant data-overhead, physical Ethernet, or phase-aligned L2 claim; [packet accounting](../../evidence/performance/v2/b1-packets-e2c75b59/REPORT.md) |
| Adversarial checks | MEASURED 13 fail-closed executable cases pass at their recorded source | Replay, tampering, bindings, expiry/revocation/generation, downgrade, unauthorized/forged identity, malformed input and failure/recovery; final regression refresh remains pending; [matrix](../../evidence/security/adversarial-campaign-b7df259b/summary.md) |
| Private origin | MEASURED three Docker network lifecycles deny client/ISP-A DNS/IP direct probes, then return the exact authorized body with one origin request | Local topology, shared test bootstrap material, no host/root resistance claim; [isolation](../../evidence/security/isp-isolation-f831c9bb/REPORT.md) |
| Federation | MEASURED admission preflight separately from route isolation; live runtime federation NOT_PROVEN | No independent-operator live-federation claim |
| Linux | MEASURED six restricted Docker Linux compatibility repeats pass | Docker Desktop VM, not bare-metal/server/NIC scaling; [Linux control](../../evidence/performance/v2/linux-compatibility-3644c324/REPORT.md) |

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
The reviewed source snapshot containing native bind support and its dependency
gate repair is `30af3c5c07b3305b67f489622b59302b44817e0c`; it can fill the
finite runbook SOURCE_SHA parameter. No new mandatory Administrator command
has been established; see the
[Administrator ledger](ADMIN_REQUIRED_FINAL_VALIDATION.md).

Current campaign recommendation: **MORE ENGINEERING REQUIRED**. This brief is
not a readiness endorsement and must be rewritten around the final accepted
state before a funding evidence freeze.
