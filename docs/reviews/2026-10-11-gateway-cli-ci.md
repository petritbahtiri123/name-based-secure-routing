# Gateway CLI CI selection follow-on

The role/reuse inventory identified substantial existing client, Windows SCM
storage, resolution, Edge and deployment work. It also showed that the existing
gateway CLI process tests were absent from the explicit Python core profile,
although all four underlying gateway library suites were selected. Last night's
connector-selection patch did not add this file.

One new selection regression failed (zero occurrences of test_gateway_cli.py).
A one-line CORE_TESTS addition now selects it exactly once on both configured
Python CI platforms. No workflow file or security contract was altered in this
follow-on. The existing seven CLI tests cover deterministic planning/no input
mutation, stable verify exit codes, resolver-last rollback planning, bounded
redacted rejection, explicit paths/entrypoint declaration and the example profile.
These are real offline subprocess checks over fixture snapshots, not installed
gateway startup, real policy application, SCM lifecycle or production acceptance.

Focused regression: one pass after the retained red failure. Gateway CLI and its
four neighbors: **65 passed**. Complete CI regressions: **24 passed**. Existing
JSON-syntax YAML/security-contract validation, full CI Ruff and diff checks pass.
Independent review found no blocking findings; reviewer did not rerun tests.
All four supervised runs were bounded, with no resource abort and all direct
children reaped. No build, network trial, service operation, credential creation,
dependency download or OS/security change was needed. Python 3.14 Windows local
results do not establish the hosted Python 3.13 or Linux matrix. Hosted schema/
execution remains unrun. Full core profile was not rerun for this one-file addition.

Remaining integration gates: explicitly provision the existing Task 4 process
harness inputs under a reviewed scope; separately validate actual installed-client
SCM lifecycle and its unexecuted different-identity storage case. Real authority,
revocation/timers and customer-origin composition remain stage-specific gates.
None were replaced with mocks or marked passed. Stages 1–2 remain 2/10 complete;
Stage 3 remains partial. Current work is local, unstaged and uncommitted on
codex/nbsr-v3-wp0-wp1 at c7abbc4423a9ad05cea9cdf6678c231a34cafd59. No hosted
dispatch, publication, protected-branch bypass or installation was performed.
