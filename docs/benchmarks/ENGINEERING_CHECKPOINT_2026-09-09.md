# NBSR engineering checkpoint, 2026-09-09

**MORE ENGINEERING REQUIRED. This is not a final funding freeze.**
The weekly usage meter reached29% against the user-authorized30% ceiling.
This checkpoint preserves remaining work; it does not declare it exhausted.
The approximate85-90% checklist estimate is not a completion-time guarantee.

## Repository and improvements

Continuation start:09a669a343330b381c67605114338cdc87d420e4.
Engineering/evidence history through a9595aa4 is recorded in
[evidence commit sequence](../../evidence/performance/v2/quality-checkpoint-a9595aa4/commit-sequence.txt).
8a603b0d adds the quality package and authority blocker. Final documentation
commits follow; use git rev-parse HEAD for the resulting checkpoint SHA.
main and origin/main remain1938154d498b32d81a3564319969430644e8a688; no push.

This continuation added a separately named authenticated keepalive B3 workload,
verified the Linux owned-process exit transition, retained failure-only UDP
socket observations, and repaired fixture provenance/PoC inventory reporting.
No Linux production default or frozen security/wire contract was optimized.
The earlier campaign's bounded Windows UDP receive-buffer change remains a
separate measured production change; it is not a new change in this continuation.

## Scoreboard, with source and scope preserved

| Evidence | Result | Qualification |
| --- | --- | --- |
| Windows 16KiB/8,07096c08 | 1.050835 Gbit/s STABLE;1.155600 DEGRADED;1.108855 SATURATED | Short finite, one physical-core allocation; not sustained/server capacity |
| Historical Windows four-core,53468db4 | 2.306118 Gbit/s strict-stable | Recorded shape/stage;3.666140 peak is DIAGNOSTIC |
| Linux 16KiB/8,40b277fb | 3.235685 Gbit/s finite STABLE | One guest CPU in Docker/WSL; observer separately unqualified |
| Linux finite mixed admissions,2a30272e | 125 offered/s ->119.313320 STABLE;150 ->142.418287 DEGRADED;200 ->111.350407 SATURATED | 23 valid records, zero invalid; not sustained admissions/core |
| B3 active bundles,0124f8ad | 2048 passes five repeats each on two/four guest CPUs;4096 fails | Clean final ownership; no global scale ceiling |
| B3 process memory at2048 | Combined role medians1,404,301,312 /1,408,299,008bytes | Two/four guest CPUs; includes QUIC/runtime/allocator/fixtures, not pure NBSR object cost |
| Same-process lifecycle,40b277fb | 500 clean cycles; zero FD/thread growth | Retained-memory cause and general plateau INCONCLUSIVE |
| B5 preparation,0124f8ad | Three completed300s diagnostics at2.234392-2.239248 Gbit/s; three failed prefixes | Mixed warmups, not one stable cohort; continuous ownership NOT_MEASURED; no qualified60/120-minute soak |
| Wire evidence | 20 matched captures/10 pairs retained | No universal fixed NBSR overhead or measured Ethernet/L2 claim |

Larger Linux receive buffers did not produce a reliable2048 one-CPU result.
All six marker-location attempts also failed. Isolated polling CPU cost is
DIAGNOSTIC, not proof of the sole handshake cause. Longer warmup completed2/3
versus1/3 short diagnostics; it was not adopted as a proven fix. Every failure
is preserved. No global hardware or production implementation ceiling is proven.

## Security and validation

Accepted adversarial evidence remains13 PASS/0 FAIL/1 isolation INCONCLUSIVE
at its source; separate three-lifecycle Docker isolation evidence closes local
private-origin reachability in its specified topology. Neither establishes WAN,
host/root resistance or live independent-operator federation. Federation admission
preflight and runtime federation remain separate; runtime federation is NOT_PROVEN.

Fresh quality checks:384 Rust tests pass, two existing ignores; release all-target
clippy with -D warnings and fmt pass.834 Python performance tests pass, three
existing skips; scoped Ruff/dependency/privacy checks pass. Four Go module race
suites and all five module vet runs pass. The independent federation module's
current-package test FAILS closed on its historical trust-anchor mismatch.
See [authority blocker](FEDERATION_PACKAGE_AUTHORITY_BLOCK.md). It already exists
at the continuation start and was not hidden by changing the trusted digest.

## Remaining work and classifications

- COMPLETE: scoped fixes, preserved repeated evidence, successful Rust/Python and
  four-module Go race verification, packet accounting and accepted local isolation.
- UNRESOLVED: B5 p99/private-memory attribution and qualified sustained soak;
  larger one-CPU B3 handshake progress and actual global production/host limits.
  Further safe engineering remains; this is a budget checkpoint.
- ADMIN_REQUIRED: the single Windows Direct paced CPU command in
  [the administrator ledger](ADMIN_REQUIRED_FINAL_VALIDATION.md). No new elevated
  requests were added and no repeated rejected ETW capture is required.
- EXTERNAL_HARDWARE_REQUIRED: native Linux/server/NIC validation. The existing
  runbook supplies executable Linux B3/B4/B5 subsets; full multihost/wire
  portability remains PARTIAL. No server results were fabricated.
- BLOCKED_ARCHITECTURAL: independent federation package trust/version alignment;
  existing P1E fresh-RouteGrant acquisition contract remains a separate boundary.
- BLOCKED_DESTRUCTIVE: none performed or required in this continuation.
- OPTIONAL_LOW_VALUE: repeating rejected buffer/location/ETW probes without new
  attribution. Safe cache cleanup recovered about1.01GB; all evidence was retained.

Safe outreach claims describe measured, source-scoped local prototype behavior
and reproducible failures. Do not claim production/WAN/ISP capacity, qualified
long-run stability, a hardware ceiling, globally green conformance, a constant
wire tax, or live runtime federation. The working funding brief remains a draft.

## Evidence index

Under evidence/performance/v2:
- linux-resource-scale-0124f8ad: ca18b36972622385359f46cef65a5e72661031b68ef422fa2b89e40249b5e5c8
- b3-marker-location-0124f8ad: 693ce92dacd8bd3eb435c4daa3ddc870fa797aecaa235a1d0836ba3cf8e45a3e
- b5-16k8-preparation-0124f8ad: 5b3d5e819d4700b05e53bf74917c9d6ac247d9fd0a1f695d172ecf459a6feb58
- quality-checkpoint-a9595aa4: c2bce7e86a8b5a54fb0edbd32841ed157d975bf451da4f63227de29212532a53

These are checksums.sha256 index digests. Each raw-evidence.json locates the
retained raw roots and indexes. Commands, failed setup attempts, source/binary
bindings and limitations remain in those packages. Do not modify sealed roots.

Final scoped integrity at8a603b0d: 21 packages, 280 canonical files and 40603 raw entries verified, including Git blob identity and canonical secret-marker checks.
Report:C:/NBSR-build/continuation-integrity-september9-8a603b0d.json
SHA-256:41c96f76bcf18e955c8e7e7dfe09d2efacd774396376cb792c8f25965593a86a
