# Native 50-cycle same-process lifecycle diagnostic

Implementation b7672a57. MEASURED Docker/WSL namespace evidence: three repetitions,
150/150 sequential authenticated connection/session/channel/materialized-stream
round trips PASS. Each role retained one PID/start-time epoch per trial. Six owned
PIDs were absent before container stop. Both final eleven-counter reports and all
150 source per-cycle closed reports were zero. Destination per-cycle closed
ownership was not measured separately.

Final cooldown RSS repeat CV: source 1.369863%, destination 2.0%; the predeclared
rule stopped after three repetitions. Source final RSS: 9.0–9.25 MiB; destination:
6.125–6.375 MiB. Cooldown FD/thread counts stayed source 6/1 and destination 8/2.

DERIVED from retained local cooldown medians: source first-to-last RSS growth was
exactly 3 MiB in every trial; second-half and final-ten slopes were zero in all
three. Destination growth was 256–384 KiB. Two trials had flat second halves; one
retained a 128 KiB step within the final ten cycles (slope 19,859.39 bytes/cycle).
Full destination slopes were 4,028.14–5,047.77 bytes/cycle. The unfavorable step is
retained. Do not call the entire destination series flat, RSS growth a leak, or
the source plateau proof of allocator cause/general leak freedom. Memory cause
is INCONCLUSIVE. Private/PSS and qualified bytes/resource were not measured.

Declared long workloads receive four seconds/cycle for hold/cooldown plus the
existing 120-second control allowance (50 cycles: 320 seconds). Existing lengths
through 16 retain 120 seconds. Transport/readiness/cleanup/transfer timers are
unchanged. This followed successful 16-cycle trials, not a failed-run timeout
extension. Request RTT includes a deliberate two-second materialization hold;
it is not data-plane performance latency.

19 literal RED cases; 168 affected tests, Ruff and focused independent review
PASS. Release Rust hashes match the prior stage. No production Rust/Go, wire,
security or trust change. This closes the native 50-cycle execution gap, not B3,
qualified memory, sustained capacity or physical-server acceptance.

A verified inactive Cargo cache with an explicitly empty tmp directory was cleaned:
156,827,648 measured host bytes recovered. Inventory/commands/results retained;
no source, private fixture, Git or authoritative evidence removed.

Reproduction: docs/benchmarks/NATIVE_SAME_PROCESS_CYCLES.md; raw run.py/setup.py,
configs, release manifest and commands. Analysis:
python -B evidence/performance/v2/native-cycles50-b7672a57/analyze.py C:/NBSR-build/native-cycles50-b7672a57

Open: native per-axis channel/stream scale, qualified private-memory measurement,
material retention attribution, full portable matrix and physical-server validation.
