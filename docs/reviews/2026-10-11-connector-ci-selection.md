# Connector CI selection audit — October 11

The existing protocol directory selection already covers both connector vector
suites. Four root Python connector suites, adjacent offline config tests, tagged
Go connector tests, quick Rust connector targets and the Node registration
verifier were absent. Extended Rust selected nonignored tests only; it never
executed the isolated loopback. Local historical connector counts did not prove
hosted selection or success. docs/CI.md coverage and status now state this scope.

The existing profiles now explicitly select those offline checks. The existing
manual workflow adds connector-loopback, reusing pinned Go 1.26.5 and unchanged
module dependencies. It prebuilds Rust, compiles an owned temporary Go worker,
then invokes exactly the ignored loopback test. Each command is supervised
directly, with 90 seconds execution plus existing bounded cleanup. Three command
bounds are not a cumulative 90-second job promise. No nested wrapper remains.
Worker cleanup and restoration of prior environment are covered on build failure,
live failure and success. Hosted cancellation still relies on runner teardown.

## Measured local results

- Selection regressions: two failures before wiring, retained.
- Initial sandbox check: 19 passes and four permission/process-cleanup failures,
  retained. Fresh test-owned temp roots and the existing host execution path
  resolve these environment limitations without weakening assertions.
- Final CI tests: 23 passed, including actual descendant termination.
- Newly selected root Python/config scope: 297 passed, no exclusions.
- Exact tagged Go test and vet commands pass using warm offline caches.
- Node verifier: 19 artifact hashes and 34 transitions across four traces pass.
- Exact new manual profile: all three commands pass, 21.48 seconds supervised;
  one Rust test wraps 19 passing loopback cases, 19 confirmed reaps.
- Quick Rust selection matches the earlier retained 23-pass/one-ignore command;
  it was not repeated solely for this wiring change.
- JSON-syntax YAML parsing, selected workflow security contracts, full CI Ruff,
  command listing, diff inspection and whitespace checks pass. These are not a
  complete GitHub-hosted schema or execution check. Hosted CI was not run.

Independent review initially caught a POSIX nested-process-group cleanup flaw
in an intermediate wrapper. It was removed before final validation; the final
direct-supervision delta received a clear review. Reviewer did not rerun tests.
A PowerShell quoting attempt to modify workflow JSON failed with SyntaxError
before writing; the subsequent structured patch succeeded.

Nine supervised runs are retained, two failed, none resource-aborted, all direct
children reaped. The PID-only cleanup check initially reported PID 15040; separate
identity inspection showed unrelated WmiPrvSE PID reuse. No worker process, task
UDP endpoint or temporary worker directory remained. No unrelated process was
terminated. Three failed-test empty directories were already absent at inspection.

## Limits and next gate

No workflow permissions, secrets, credentials, runner selection, branch safeguards,
dependency versions or frozen authority/evidence were changed. No local dependency
download, publication or hosted trigger occurred. Real loopback TLS/exporter
success still uses fixture authority/revocation and logical time; Stage 3 remains
partial and stages 1–2 remain 2/10. Python 3.14 local results do not establish the
hosted Python 3.13 or Linux matrix. All prior five fixes and evidence remain intact.

This bounded selection audit has no remaining evidenced local wiring gap. Its
next validation is a published hosted run, which requires separate publication/
dispatch authorization. Real authority/timer/provider integration remains outside
this task; no new policy choice was made. This is not a claim that every possible
overnight improvement is exhausted, and no broad audit was started to fill time.
