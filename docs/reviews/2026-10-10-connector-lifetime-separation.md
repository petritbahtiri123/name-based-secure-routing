# Connector mock lifetime separation

Base: c7abbc4423a9ad05cea9cdf6678c231a34cafd59. Mock-only bounded correction,
implementing the already accepted distinctions in V3 section 14, F93, P2D and
Tranche 5/6. No real connector authority mapping or profile limits are selected.

Design: replace ambiguous Permission.expires and the lease_bounds_active switch
with explicit admission_expires, active_expires and CompletionGrace(profile,
seconds) fake verifier inputs. Active work captures its request bound, authority
bound and grace context. Registration/admission expiry withdraws new-use
eligibility and starts a non-extending drain from the actual expiry instant.
Deny-new starts drain at the event time; terminate-active overrides it immediately.
A separate renew_work operation, before expiry and while eligible, refreshes the
same work object's authority without changing its owner/session or replaying it.
The requested deadline remains a hard upper bound. Grace never extends authority.
Verifier None remains invalid/unsupported input, not a model of ordinary outage.

All values and profile labels are test inputs. Real signed-policy provenance,
credential mapping, F93 outage distinctions and asynchronous behavior remain open.
Implementation/test results will be recorded below; no new commit or push authorized.


## Results and retained evidence

Published baseline CI: run 38067741432 completed successfully for exact
c7abbc4423a9ad05cea9cdf6678c231a34cafd59. All seven jobs succeeded: node-policy,
Python Ubuntu/Windows, Rust Ubuntu/Windows and Go Ubuntu/Windows. This does not
validate the new uncommitted model patch.

Local sequence (all zero skips):
- connector-lifetime-red: 12 setup assertion errors, 72 deselected; explicit
  CompletionGrace was missing. This is API absence evidence, not 12 behavioral
  failures. No attempt is discarded.
- connector-lifetime-green: 121 passed (84 model + 13 state + 24 revocation).
- Independent review found two boundary bugs. connector-lifetime-grace-red:
  2 failed, 1 passed, 84 deselected (shorter grace ignored before/after drain).
- connector-lifetime-renew-red: 1 failed, 87 deselected (15-to-16 clock samples
  at narrowed admission expiry incorrectly cancelled independently valid work).
- connector-lifetime-final: 125 passed (88 model + 13 state + 24 revocation),
  pytest 1.03 seconds; supervised elapsed 2.22 seconds. Ruff check and formatting
  passed; scoped source/document diff check passed with existing CRLF warnings.
- Independent narrow rereview inspected both corrections and found no remaining
  blocker; reviewer did not repeat tests. These are implementation-agent results.

Raw logs, resource/command manifests, final source snapshots and scoped patch are
under evidence/connector-control-model/2026-10-10/ with connector-lifetime prefixes.
Historical raw pytest whitespace is retained unchanged. Intermediate dirty source
snapshots were not captured per red run; those logs identify base commit and
commands but are not standalone exact intermediate-source reproductions. Final
source and patch hashes accompany this report in JSON.

Every supervised child was reaped, with no resource abort. Final run disk free
12310224896 bytes and RAM free 4591374336 bytes; no build/download/container was
performed. Subsequent Get-Process showed no visible Python process. The supervisor
used 95-second work bound, 8-GiB disk start/6-GiB floor, stricter 256-MiB growth
limit and 2-GiB RAM reserve. No process-cleanup counts were fabricated.

Documentation upkeep encountered a cp1252 UnicodeDecodeError on the plan; prior
profile decoding was corrected from exact HEAD UTF-8 bytes before reapplying only
the intended scoped prose. No failed runtime check was hidden. AGENTS now records
the explicit lifetime fixture semantics. Historical 109-test reports are unchanged.

Limitations: synchronous deterministic fakes, one work slot, explicit polling;
no cryptographic verification, IO, wire changes, persistent revocation, production
mapping or ordinary-outage handling. Changed profile fails closed. Work renewal
while draining is unimplemented, not forbidden by protocol. Stage 1 remains partial,
0/10 package milestones complete. No commit, push, bypass or next-stage work in
this iteration. Paused-peer, mixed historical checkpoints and unrelated files are
preserved; the overnight checkpoints receive only a new current entry.
