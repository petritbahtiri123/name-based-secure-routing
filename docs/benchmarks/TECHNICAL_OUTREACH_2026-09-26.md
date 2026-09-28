# NBSR: request for an independent technical evaluation partner

NBSR is a security-focused transport and admission prototype being evaluated for
controlled access to isolated private origins. We are seeking an ISP, cloud,
university or infrastructure partner with dedicated Linux/server hardware to
reproduce its local results and evaluate deployment requirements.

## What is demonstrated

- **MEASURED, scoped Windows soak:** three one-hour NBSR runs at 75% of a fresh
  one-core reference completed 31.14 million operations without errors/timeouts,
  with verified final cleanup. Median 0.754762 Gbit/s; continuous ownership
  observer qualification remains open, so full B5 acceptance is not claimed.

- **MEASURED, Windows loopback:** a scoped four-physical-core workload achieved
  2.306 Gbit/s strict-stable throughput across five repeats. This is a historical
  workload-specific result, not WAN capacity or a final-binary certification.
- **MEASURED, local native namespaces:** three 2048-connection functional/resource
  trials completed with verified endpoint cleanup. Three 4096-connection attempts
  failed before common active hold and are retained; no production ceiling is
  inferred.
- **MEASURED, Docker isolation:** three fresh private-origin topology lifecycles
  passed authorized access and twelve negative reachability probes. Origins were
  not published to the client network. This is local PoC isolation evidence.
- **MEASURED, scoped adversarial campaign:** replay, tampering, binding, expiry,
  revocation, generation and related negative cases have source-bound evidence.
  This is not an independent security certification.

The approved route is client → non-frozen ISP-A adapter → unchanged NBSR secure
path → non-frozen ISP-B adapter → Origin Connector → isolated private origin.
Security checks, wire formats and trust authority are not weakened for speed.

## What we are not claiming

Server/ISP/WAN capacity, linear multicore scaling, a qualified near-ceiling
60–120-minute soak, isolated per-resource memory costs, or live independent
runtime federation are **NOT_PROVEN**. Federation admission preflight is a
separate result. Diagnostic peaks are not stable capacity. Some Windows
profilers have failed capture or observer-quality checks; those failures remain
in the evidence and do not establish an NBSR limit.

## Proposed collaboration

Provide an otherwise idle dedicated Linux host (and preferably a second host
and physical NIC path), record CPU topology/RAM/NIC/OS/toolchains, and reproduce
the matched secure Direct/NBSR workloads. Begin with clean source/build binding,
functional/security checks and telemetry qualification; then run core scaling,
admission, resource lifecycle and sustained stability. Preserve all valid runs,
including unfavorable results. Agree on deployment and threat-model questions
before attempting any live federation authority change.

The immediate request is **technical evaluation and pilot scoping**, not a claim
of production readiness. Funding discussions can support validation and
engineering milestones without representing open gates as completed.

## Evidence supplied on request

The [latest checkpoint](ENGINEERING_CHECKPOINT_2026-09-26.md) and its historical index bind the
scoreboard to source, workload and evidence paths. The
[external validation definition](EXTERNAL_LINUX_SERVER_VALIDATION.md) records
hardware, telemetry and acceptance requirements, including incomplete portable
matrix coverage. Raw artifacts have local checksum indexes; transfer and
off-host backup must be arranged explicitly. No external results are fabricated.

Status: **READY FOR TECHNICAL OUTREACH WITH EXPLICIT LIMITATIONS**.
