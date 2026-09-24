# NBSR engineering checkpoint, 2026-09-24

Start SHA a7a57b0d0d0cb65f41065d1854b35c53affe29c4, feature branch
codex/nbsr-v3-wp0-wp1. Main/origin-main remain
1938154d498b32d81a3564319969430644e8a688. No push or production/security change.
Budget baseline 31% weekly used; user allows up to 60 additional points (cap 91%).
This is an in-progress engineering checkpoint, not full campaign closure.

## Native forwarding control completed

- 0866ca47: bounded private finite peer coordination, reused transport/collection
  and independent pair gate, parser reuse, optional injected event ledger.
- f3814929: measured NBSR early-exit/controller-ACK mismatch fixed. Direct lifetime
  ACK unchanged; NBSR controller ACK kept outside sealed peer evidence. Fixed
  controller deadline and EOF cancellation remain enforced.
- Corrected cohort: 5/5 Direct plus 5/5 NBSR complete; six live-PID EOF controls
  pass, with independent exact-PID absence under the peer UID after cleanup.
- Diagnostic medians: Direct 1.905323 Gbit/s, NBSR 1.929450 Gbit/s; CV 15.98% and
  21.71%. No strict-stable ceiling, causal speedup, hardware or WAN claim.
- 115 focused tests, independent focused review/scoped fix review, exact release
  rebuilds with unchanged Rust hashes, raw/transcript/privacy/integrity gates.

Evidence: `evidence/performance/v2/native-finite-coordinator-f3814929`.
Runbook: [finite native coordinator](EXTERNAL_NATIVE_FINITE_COORDINATOR.md).
Initial failed controller cohort and failed network setup remain retained.

## Evidence correction

[Placement erratum](NATIVE_PLACEMENT_ERRATUM_2026-09-24.md): shared 1024 repeat 3
failed before active during handshake, not after activation/close. Repeat 2 has
measured held-idle timeout exposure; repeat 5's shorter diagnostic intervals do
not establish the same cause. Overall 2/5 versus 5/5 verdict is unchanged.
Legacy /proc scans that skip PermissionError are not independent absence proof;
retained owned-process exit/reap and group-cleanup evidence has its own scope.
The canonical summary/checksum were corrected without changing raw evidence.

## Remaining work

Native post-close report binding is complete at ac40740c: 5/5 NBSR and 5/5
Direct finite pairs pass, all requested NBSR reports show eleven zero counters,
and all twenty owned PIDs are absent before fixture stop. Evidence:
`evidence/performance/v2/native-post-close-ac40740c`, 592 raw files verified.
Diagnostic medians 2.395090 Direct / 2.496439 NBSR Gbit/s; CV 16.12% / 12.17%.
These are not strict-stable references. The paired on/off experiment is now
REJECTED_OBSERVER_GATE: five uninterrupted pairs show median -5.3273% goodput,
+63.0342% p99, off/on CV 25.36% / 32.28%. All twelve cells pass functional
cleanup; interrupted pair 3 is retained and one sixth pair supplies the fifth
uninterrupted comparison. High variance prevents causal attribution to the
observer or production code. Package:
`evidence/performance/v2/native-post-close-observer-ac40740c` (718 raw files).

Short paced native integration is complete at 5595e45f: 5/5 Direct and 5/5 NBSR
functional passes at 1,000 offered ops/s, 16 KiB / eight streams / depth one.
Achieved/offered: Direct 99.75â€“99.93%, NBSR 99.70â€“99.99%; median goodput including
drain 0.261677 / 0.261822 Gbit/s. Zero errors/timeouts, all requested reports clean.
Retained p99 drift violations in 3/5 Direct and 1/5 NBSR prevent a stability claim.
Package: `evidence/performance/v2/native-paced-5595e45f` (600 raw files verified).
122 affected tests, Ruff and focused independent review passed; follow-up
b2bd7141 binds cohort comparison identity to post-close mode (RED/GREEN,
21 affected tests and scoped re-review). No production changes.

Reusable observer/reference qualification gates are implemented at 9ed3c5a2.
Retrospective validation correctly rejects the retained ac40740c observer and
reference cohorts; both finite ladders remain UNRESOLVED. Package:
`evidence/performance/v2/native-reference-gates-9ed3c5a2`. Initial 65 affected
tests and final 24 gate tests, Ruff and focused review passed. No new performance
run or production change. Qualified native reference evidence and full paced B5
orchestration with live resource guards remain open; short diagnostic integration
and read-only gates do not close them.
Same-process memory observer qualification, current
qualified physical-core forwarding/admission references, actual near-ceiling
60/120-minute soak and final whole-package acceptance remain open. Historical
Windows throughput/admission results remain as previously scoped; none are
superseded by these diagnostic native functional trials.

ADMIN_REQUIRED: existing Direct paced CPU capture only. EXTERNAL_HARDWARE_REQUIRED:
real independent Linux/server hosts, physical cores/NIC and WAN validation.
BLOCKED_ARCHITECTURAL: accepted live federation authority/version mismatch.
No destructive action required. Private-origin isolation and adversarial evidence
retain their earlier exact-source scope; live runtime federation is not claimed.

Safe cleanup removed only 20 stopped verified campaign fixtures and one empty
owned network after raw retention. Logical Docker space freed 617,537,536 bytes;
no measured host SSD recovery (delta -344,064 bytes). No source/Git/raw evidence,
images, credentials or unrelated data deleted.

Subsequent disk-reserve stop triggered safe Cargo cleanup of five verified inactive
targets, recovering 4,635,074,560 bytes across the measured maintenance interval.
The interrupted observer run was resumed without deleting any result. Inventory,
commands and before/after values are retained in `native-observer-cleanup-20260924`.

Another 76 stopped fixtures were removed after complete raw/endpoint index checks:
2,368,540,672 logical writable bytes, no measured host SSD recovery. Inventory is
in `native-closed-fixture-cleanup-20260924`, referenced by the paced package.

Native local live-guard prerequisite implemented at 7d5cbcf1: bounded per-host
resource/progress accounting, existing drift/growth thresholds, no cross-host
monotonic comparison. 68 affected tests and Ruff PASS, scoped review clean.
Package `evidence/performance/v2/native-local-live-7d5cbcf1` retains synthetic
RED/GREEN evidence. Not integrated into peers yet; observer and soak unqualified.

Source-only live observer integrated at 55e83c2e, with unchanged short workload
and deadlines. Five Direct/five NBSR cells functional PASS, zero errors/timeouts,
20 owned PIDs absent and requested NBSR counters clean. Median goodput
0.261742/0.261612 Gbit/s at 1,000 offered ops/s; p99 drift fails 3/5 each.
29â€“30 evaluated private-resident samples/source, no short-run growth predicate
failure. Observer neutrality and destination memory NOT_ESTABLISHED/NOT_MEASURED.
138 affected tests and Ruff, review/re-review PASS. Package
`evidence/performance/v2/native-source-live-55e83c2e`. This remains pairwise
diagnostic evidence with fresh-per-repeat authority; generic cohort authority
gate is not weakened. Full native relay/destination live guards remain open.

Paired native live telemetry completed at 94209a9c: both endpoint-local guards,
ordered source progress relay, independent raw joins. Literal RED exposed and
fixed reentrant control-writer reordering; 179 affected tests/Ruff/re-review PASS.
Five Direct/five NBSR cells functional PASS at 1,000 ops/s; medians
0.261756/0.261911 Gbit/s, p99 drift failures 3/5 and 2/5. Six controlled EOF
trials PASS after both guards were active; 12 owned PIDs absent. Package
`evidence/performance/v2/native-paired-live-94209a9c`. No production change.
Short paired integration is complete; matched observer qualification, qualified
reference and genuine reference-bound near-ceiling long-duration execution remain
open. Do not promote these short diagnostic results to B5 acceptance.

Matched paired-live observer qualification at the same 94209a9c release now
REJECTED_OBSERVER_GATE: all ten NBSR cells functional/cleanup PASS, median paired
goodput effect -0.049127%, p99 +29.339579%; throughput CV off/on 0.093985/0.127981%.
Window-p99 summary CV is 67.48/64.79%, so causal observer attribution is not
defensible. Preserve the rejection; no repeat-until-PASS or production change.
Package `evidence/performance/v2/native-paired-observer-94209a9c` also retains a
historical ac40740c CPU calculation: both peers together occupied median
95.91/97.70% of their allocated guest CPU over overlapping sampled lifetimes.
This is not a physical-core/whole-host ceiling or steady CPU ns/op.
During package construction, the privacy gate rejected generated binary Python
caches. Their proposed deletion was blocked by automatic policy; the two .pyc
files were instead preserved outside the evidence package under
`C:/NBSR-build/paired-observer-analysis-cache-20260924`, then the new package was
sealed and verified. No raw evidence was deleted. Qualified timing remains open.

Explicit longer diagnostic support at 4144d8fa now passes three matched 60-second
Direct/NBSR pairs (six functional cells, zero errors/timeouts, twelve owned PIDs
absent, NBSR eleven-counter cleanup zero). Medians 0.261531/0.261372 Gbit/s at
1,000 offered ops/s are diagnostic only. p99 drift fails 2/3 Direct and 3/3 NBSR;
source private-growth predicates fail 1/3 and 2/3, destination 1/3 and 0/3.
These are retained numerical failures, not established leaks or stable capacity.
Default short contracts remain unchanged. 147 affected tests/Ruff, synthetic
two-hour replay and review/re-review PASS. Package
`evidence/performance/v2/native-long-4144d8fa`. Three inactive Cargo caches were
cleaned with measured 743,329,792-byte recovery; inventory retained in the package.

Reference-bound native diagnostic orchestration is implemented at fa0e4d7e.
Exact 70â€“80% rate and current source/shape/stable-depth/bind checks precede launch;
actual placement/build and unchanged reference evidence gate publication after
collection. Live observer and sustained-capacity labels remain NOT_ESTABLISHED.
Initial 36 affected tests, final 24 runner/reference tests, Ruff and focused review
PASS. The real retained ac40740c reference rejects before child output, as required.
Package `evidence/performance/v2/native-reference-run-fa0e4d7e`. This closes the
orchestration prerequisite, not qualified native reference or actual B5 acceptance.

External capability inventory refreshed: four real Linux CLI interfaces PASS;
three focused matrix tests PASS after literal RED. Existing native phase/socket
coverage is distinguished from physical/continuous ownership gaps. Full matrix
remains PARTIAL_REQUIRED_PORTING, with per-axis remote same-process lifecycle
cycles and full executor still open. Evidence: external-capability-refresh-20260924.

Native same-process cycles: bounded sequential command/barrier/ledger/driver
prerequisites implemented; 114 affected tests/Ruff/re-review PASS. Review exposed
and RED/GREEN fixed premature completion markers accepted between polls. Existing
bundle behavior retained. Endpoint integration, collected-evidence/process-epoch
validation and actual cycle runs remain OPEN; no measured cycle claim from helpers.
Raw prerequisite tests: C:/NBSR-build/native-cycle-contract-tests-20260924 (sealed).

Native same-process endpoint/runner integration now implemented: separate cycle
schema, no offered-rate/fanout controls, shared bounded cleanup/collection, exact
sequential command and process-epoch checks, retained per-cycle socket/events and
final eleven-counter cleanup. 19 literal RED cases preceded integration; 133
affected tests/Ruff and focused independent review PASS. Actual release namespace
trials are next; no measured cycle result yet. Runbook: NATIVE_SAME_PROCESS_CYCLES.md.

September 25: native same-process cycle integration at 4375d7ac passes three
four-cycle and three sixteen-cycle namespace trials (60/60 cycles), plus six
catchable control-EOF trials. Positive source per-cycle and both final ownership
reports are zero; cooldown FD/thread counts remain source6/1 and destination8/2.
Initial RSS growth is retained without allocator/leak attribution. Sixteen cycles
do not close the 50-cycle external memory gate. Canonical package
`evidence/performance/v2/native-cycles-4375d7ac`: 5 canonical/privacy6/raw1318 PASS.
No production/security change or new throughput/capacity claim. Next: bounded
50-cycle workload to investigate whether cooldown retention keeps growing.

September25: declared native cycle lengths10/25/50/100 supported for external
50-cycle validation. Existing<=16 controller budgets stay120seconds; longer
workloads use4seconds/cycle plus120seconds control allowance. Transport and
readiness/cleanup/transfer deadlines unchanged. 19 literal RED,168 affected
tests/Ruff and scoped review PASS. Actual50-cycle namespace trials are next.

September 25: native 50-cycle workload at b7672a57 completes three repetitions,
150/150 cycles, six owned PIDs absent, both final/source per-cycle eleven-counter
ownership zero. FD/thread counts remain constant. Final RSS CV 1.37%/2.0% keeps
three repeats per the declared rule. Source second-half RSS is flat in all three;
destination is flat in two and retains one 128 KiB late step. Cause INCONCLUSIVE,
not a leak or allocator claim. Native workload-length gap closed; qualified
private-memory/per-axis/full B3 closure remains open. Package native-cycles50-b7672a57
passes 5 canonical/privacy6/raw1411 integrity checks. No production change.

September25: native per-channel stream scale at b9a29408 passes3 repeats each
16/32/64 streams,4cycles:36/36 cycles and1344/1344 round trips.18 owned PIDs
absent; source per-cycle/both final ownership zero; cooldown FD/thread6/1 and8/2.
RSS repeat CV<2.16%; no5-repeat extension required. Canonical native-streams-b9a29408
retains all raw evidence and independent replay. Diagnostic RSS totals only;
no qualified bytes/stream, allocator, throughput or physical-hardware claim.
Channel scale and qualified memory/B3/B5 closure remain open. No production change.
