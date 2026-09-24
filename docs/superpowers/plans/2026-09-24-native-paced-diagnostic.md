# Short native paced diagnostic

The private finite coordinator now joins native peers and validates optional
post-close ownership. Its command path cannot yet launch the existing grouped B5
pacer. Add an explicitly diagnostic rate option to the same bounded twenty-second
mode. This is an integration prerequisite, not a qualified B5 reference or soak.

Keep three-second warmup, twenty-second issue duration and fixed 120-second
controller cap. Use existing B5 rate/progress flags with one endpoint group and
unchanged useful-work, TLS, ACK and cleanup semantics. Both peer metadata and
collected commands must bind the requested rate. Require post-close mode for the
paced path and reject coexistence with fixed-work or phase capture modes.

Reuse ProgressValidator for exact grouped accounting, strict bounded JSON lines,
one final record and no data after final. Store a distinct native-paced summary,
not a forged P2A repeat. Report achieved/offered, measured-plus-drain goodput and
existing drift-gate outcomes. The source is sampled and owned as before; no claim
of live private-memory drift qualification, steady CPU metrics or stable capacity.
Malformed/accounting/error/cleanup failures fail closed. A valid slow trajectory
remains a retained diagnostic with its failed performance gates visible.

RED tests cover configuration/command symmetry, invalid rate and mixed modes,
valid and malformed B5 transcripts, rate/shape/command mismatches and old finite
fixtures. GREEN uses minimal conditional integration and one focused review.
Then rebuild exact source, run minimum three matched Direct/NBSR diagnostic pairs
(five if CV exceeds five percent), retain all outcomes and verify evidence.
No production or frozen contract changes. Full paced resource/phase guards,
reference qualification and sixty-minute soak remain separate work.

Implementation verification: 21 literal RED failures, then two integration RED
failures; 122 affected tests and scoped Ruff PASS. One independent focused review
found no Important/Critical issues; requested minor error/timeout and retained
drift tests were added. Exact-source real runs follow the implementation commit.

Exact-source 5595e45f release cohort complete: five matched Direct/NBSR pairs
at 1,000 offered ops/s, all functional/accounting/cleanup checks pass. P99 drift
violations remain visible in three Direct and one NBSR cell; no stability claim.
Package `evidence/performance/v2/native-paced-5595e45f` retains all runs.
Follow-up b2bd7141 closes the post-close comparison-identity omission with one
literal RED/GREEN, 21 affected tests and clean scoped review. Full live resource
guards/reference qualification remain explicitly outside this completed step.
