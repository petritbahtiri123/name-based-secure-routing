# NBSR engineering checkpoint — 26 September 2026

Continuation start: `5553ff2c964d1d6b4359df822af78a1d7f0b9bc2`.
Engineering source: `fd138398549a579b50dd0693fc278d3998b0b3e0`.
Branch: `codex/nbsr-v3-wp0-wp1`. Main and origin/main are protected at
`1938154d498b32d81a3564319969430644e8a688`. No push or frozen contract change.

## New evidence

- **PARTIAL_B5, completed on 27 September:** three one-hour observations at
  75% of the fresh one-core reference completed 31,139,327 operations; median
  0.754762 Gbit/s, CV 0.399%, zero errors/timeouts, both endpoint eleven-counter
  reports zero. Drift guards passed. Continuous ownership qualification remains
  open; this is not full B5 acceptance. [Soak evidence and verified raw indexes](../../evidence/performance/v2/soak75-fd138398/summary.md).

- **COMPLETE, scoped Go fix:** cancel, close once and join benchmark-owned
  workers on every post-dial return. Successful completion/ACK ordering is
  preserved. Release workload 18/18 passes, 1680 round trips, 150 same-process
  cycles. Focused tests, full affected Go race suite and vet pass. This is a
  benchmark reliability fix, not a production performance optimization.
  [Evidence](../../evidence/performance/v2/go-lifecycle-scope-fd138398/summary.md).
- **COMPLETE, narrow fresh reference:** one physical core, 16 KiB/eight streams:
  1.031167 Gbit/s strict-stable at depth one; 1.159379 degraded at depth two.
  Twelve Direct/NBSR cells, three repeats per cell, all goodput CVs ≤5%.
  [Evidence](../../evidence/performance/v2/soak-reference-fd138398/summary.md).
- **INCONCLUSIVE, full Go resource attribution:** source benchmark workers are
  now explicitly accounted for; full QUIC-internal source ownership is not.
  Sampled memory retention alone does not establish a leak or allocator cause.
- **PLATFORM_DIAGNOSTIC_LIMIT, WPR:** synthetic CPU.light preflight succeeded,
  but the real benchmark's export still failed. No more blind reruns and no
  new Administrator command are pending. See the
  [admin validation register](ADMIN_REQUIRED_FINAL_VALIDATION.md).

## Retained scope

The [25 September checkpoint](ENGINEERING_CHECKPOINT_2026-09-25.md) remains the
index for historical four-core throughput, admission, native 2048 success and
4096 failure, packet accounting, security and isolated-origin evidence. None is
silently promoted to a measurement at today's source. No new server, WAN,
physical-wire or live federation result is claimed.

The [federation boundary](FEDERATION_OUTREACH_BOUNDARY_2026-09-26.md) records
the current trust-manifest mismatch without weakening the verifier. Approved
authority reconciliation is BLOCKED_ARCHITECTURAL for this bounded campaign.
Local isolated-origin tests already have accepted evidence; live independent
operator federation is separate and NOT_PROVEN.

## Remaining classification

| Status | Work |
| --- | --- |
| COMPLETE | Scoped Go worker cleanup fix and release regression cohort; fresh single-core reference; preserved WPR failure and conservative outreach draft |
| INCONCLUSIVE | Full Go internal resource attribution and qualified near-ceiling sustained stability |
| PLATFORM_DIAGNOSTIC_LIMIT | Rejected/failed Windows profiler and ownership-observer qualification; no sole production cause established |
| EXTERNAL_HARDWARE_REQUIRED | Dedicated Linux/server/NIC/WAN validation; portable matrix still requires the work explicitly identified in the external definition |
| BLOCKED_ARCHITECTURAL | Frozen federation authority compatibility; no trust-anchor substitution |
| ADMIN_REQUIRED | No new pending manual command justified by the latest WPR failure |
| BLOCKED_DESTRUCTIVE | No destructive action needed or performed |
| OPTIONAL_LOW_VALUE | Repeating unchanged WPR preflights without a new defensible capture method |

The [technical outreach brief](TECHNICAL_OUTREACH_2026-09-26.md) requests
independent evaluation and pilot scoping. It is not a production-readiness or
complete funding-grade acceptance certificate. No outreach message was sent.
