# Bounded native long-duration diagnostic execution

The live observer failed timing qualification. Do not rerun it to chase PASS or
claim a qualified soak. Independent useful work is making the native runner able
to execute and validate an explicitly different long workload on future hardware.

1. Add explicit diagnostic durations 60 (functional preflight), 3600 and 7200
   seconds. They require paced mode; old short/fixed-work contracts stay unchanged.
   Use one bounded duration contract across command, controller, telemetry,
   samplers and independent replay. Keep readiness, cleanup and transfer deadlines.
   Long workload budget is declared duration plus the existing 120-second control
   allowance, not a retry or extension of a failed short test.
2. RED first: exact source commands, rejection of malformed/unpaced durations,
   duration-mismatched final accounting, resource/progress bounds and cancellation.
   Implement the minimal plumbing and run affected tests, lint and one review.
3. Release rebuild and three matched 60-second Direct/NBSR functional trials;
   five if throughput CV exceeds 5%. Preserve failures and cleanup evidence.
   Do not run an unqualified 60-minute load and relabel it near-ceiling stability.
4. Document that reference binding and observer qualification still gate B5
   acceptance. This diagnostic capability by itself cannot claim sustained capacity.

No production, wire, security or frozen authority change. Existing short evidence
must replay unchanged. Public artifacts remain outside private fixture roots.

Implementation verification: 14 literal RED cases, then focused GREEN; synthetic
two-hour paired transcript with 1440 windows and 300 resources per role replays.
Review found a minor stale 20-second metadata description. A literal RED and
duration-derived description fix close it; scoped re-review clean. Final 147
affected tests and Ruff PASS, retained old short cohort replays unchanged.
Actual fresh-release 60-second preflight and evidence preservation follow.
