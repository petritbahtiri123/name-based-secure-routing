# Native finite forwarding coordinator

Start a7a57b0d; weekly usage baseline 31%, maximum 91%, reserve final checkpoint.
Scope: executable native Direct/NBSR finite reference coordination, a prerequisite
for paced B5. Keep the accepted finite 3-second warmup / 20-second measurement,
120-second controller and all binary/transport/security contracts unchanged.
No stable/soak classification follows merely from functional orchestration.

1. RED tests: private bounded event ledger, readiness/ACK ordering, EOF and stale
   output protection; parser reuse and optional injected ledger preserve old API.
2. Implement small finite endpoint using existing owned peer runner and nonblocking
   control reader; source owned event means fresh output, not completed TLS/preflight.
   Source waits at most 30 seconds for transferred readiness. Start destination only
   after source controller owns its fresh root; capture management startup gap.
   Existing source validation must finish and relay exit zero before destination ACK.
3. Reuse bounded relay transport, archive collection and independent finite pair
   gate. Never collect a root without a live ownership event from this invocation.
   Both role transcripts must match retained endpoint events; incomplete/nonzero
   runs fail and remain retained. Fresh roots, strict SSH host keys, no admin changes.
4. Focused regression suite and one fresh review. Atomic implementation commit,
   exact-source release build, three matched Direct/NBSR namespace repeats (five
   for CV >5%) plus bounded cancellation controls. Preserve every bad-valid result.
5. Record evidence, limitations and next paced-reference work. No production
   optimization without measured cause. Continue inside authorized budget.

The existing private management channel is benchmark control, not public protocol.
Approval gates for routine design/test execution are superseded by the user's
explicit campaign autonomy. No external SSH/hardware result is fabricated.


Scoped result complete: implementation 0866ca47, early NBSR controller-only ACK
fix f3814929, 115 focused tests and independent review/scoped fix review. Retained
initial 5 Direct passes/5 NBSR controller failures; corrected 5+5 passes; 3+3
live-PID EOF cleanup controls. Exact release hashes unchanged. Evidence and
limitations: evidence/performance/v2/native-finite-coordinator-f3814929. This does
not finish the native post-close reference or paced B5 program.
