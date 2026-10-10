# Four-failure CI portability patch

This local patch follows the published `9ac925dfa71f3bdf1641106610d0fd528e658cff`
baseline. Its hosted run remains **3 successful / 4 failed jobs**, as recorded
in `2026-10-10-hosted-ci-9ac925df.md`. No new hosted success is claimed.

## Causes and minimal corrections

- **Node setup:** the final Node core test launches Python's vector generator.
  Python setup alone does not install `cbor2`. The workflow now installs the
  constrained declared project runtime before verification. The reviewed
  omission/order regression remains included; no local downloads occurred.
- **Python Ubuntu:** the uppercase alias is rejected on both platforms. Linux
  reports a missing path; Windows resolves it before rejecting the unauthorized
  spelling. The test now validates the original fixture, changes only the path,
  and requires `CoreBaselineError` without treating OS-dependent wording as the
  contract. All five alias cases remain, plus a deterministic missing-resolution
  simulation of the Linux branch. No production validator or authority changed.
- **Go Ubuntu:** a demo command test hardcoded the Windows build hierarchy despite
  production already selecting `/opt/nbsr-build/nbsr-demo` on Linux. The fixture
  selects the existing approved platform path, never creates that build directory,
  and additionally rejects another run's build root. Runtime/bootstrap isolation
  assertions remain intact. No production path policy changed.
- **Go Windows:** test provisioning used `icacls /inheritance:r /grant:r` for
  three approved SIDs. That does not remove unrelated explicit grants. A
  deterministic test added a resolvable unapproved LocalService writer and
  reproduced the same `unapproved write ACE` rejection after old provisioning.
  The test helper now replaces the complete protected DACL and owner on its
  `t.TempDir()` child, with only the same process-owner/System/Administrators
  writers already accepted by production. The regression proves rejection
  before provisioning, acceptance afterward, and rejection again after adding
  the foreign writer back. The production allowlist and validator are unchanged.

The hosted runner's exact original offending SID is still unavailable. The
retained-explicit-grant mechanism is reproduced, and deterministic exact fixture
provisioning removes dependence on that unknown host grant. This is a test
fixture correction, not evidence that production should trust additional SIDs.
No account creation, host/global ACL alteration, OS security-setting change,
permission widening, bypassed test, ACK edit, or authority repinning is needed.

## Measured verification

All runs used provisioned tools/caches, offline dependency resolution, at most
two Go build jobs, 95-second supervisor cutoff, disk/RAM guards and task-owned
cleanup. No guard aborted. The adjacent manifest contains commands and logs.

| Check | Result | Supervised time |
| --- | --- | ---: |
| Five F75 alias cases | 5 passed, 16 deselected | 32.37 s |
| Simulated Linux missing case alias | 1 passed, 21 deselected | 13.76 s |
| Go demo command package | package passed | 32.76 s |
| Initial synthetic ACL SID | failed before reproduction: SID mapping rejected | 12.27 s |
| Resolvable ACL reproduction, old helper | expected failure: unapproved writer retained | 4.83 s |
| Corrected ACL regression | passed | 4.82 s |
| Full affected Windows authority package | passed; package runtime 16.550 s | 18.86 s |
| Full CI regressions | 17 passed | 3.62 s |

The Go text output establishes package success, not an independently counted
number of individual test/subtest passes. Earlier Node RED, local cleanup-EPERM
failures and focused cross-language pass remain in the hosted baseline record.
Ruff on changed Python tests, gofmt checks, workflow contract validation and
whitespace checks passed. Independent scoped review found no blocking correctness
or security issue; the reviewer ran no tests and made no edits.

## Limits and publication boundary

This Windows host did not execute native Linux Go or a full fresh Linux matrix.
The Linux Python branch was simulated explicitly; the Linux Go fixture follows
the unchanged production-approved hierarchy and still needs hosted execution.
The new hosted dependency installation has not run yet. The full prior Node
attempt's cleanup failures are not relabeled as passing by the focused rerun.

All four failures have a bounded local correction that preserves the intended
contract without user configuration or a security-policy decision. Confirmation
that all hosted jobs pass requires a separately approved publication. The local
commit is authorized only after verification/review; no push or further bypass
is authorized at this checkpoint. Unrelated files remain preserved.
