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
Achieved/offered: Direct 99.75–99.93%, NBSR 99.70–99.99%; median goodput including
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
