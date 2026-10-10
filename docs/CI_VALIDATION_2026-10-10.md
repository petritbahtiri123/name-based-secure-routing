# CI implementation validation — 2026-10-10

Base: `8e548588c6ff636bb7a29a8202adb9a37e5110c1` on
`codex/nbsr-v3-wp0-wp1`. This record covers the new CI configuration and runner.
The separate partial-body transport regression and overnight report remain
uncommitted and outside this change. No push or new protection bypass occurred.

## Observed local results

- Windows, provisioned Python 3.14.6 and Node 24.19.0; no local dependency
  installation or toolchain download. Hosted Python is pinned to 3.13.14.
- Final CI regression suite: **12 passed**, 3.12 seconds. It covers real
  descendant timeout termination, tree/final-cleanup failure reporting, five
  unsafe workflow mutations and checked-in workflow contracts.
- CI Ruff and structural validator passed; `git diff --check` passed with
  line-ending conversion warnings only.
- `python-core` profile and `pip check`: exit 0. The first runner version did
  not forward Windows child output, so no exact pytest count is asserted for
  that run. Explicit stdout/stderr forwarding was subsequently added.
- `node` profile: all five commands exit 0 (core tests/vectors, federation
  tests/vectors and exporter vectors). Exact TAP counts were not retained by
  the first runner version.
- Isolated protocol tests: **342 passed**, 7.49 seconds.
- Critical Python correctness lint, CI Ruff, scoped privacy scan (**121 files**),
  core vector regeneration and exporter vectors (**2 valid, 21 invalid/mutation
  cases**) all passed.

## Failed attempts and limits

- Initial regression collection failed before the runner existed, as intended.
- First generated-workflow attempt had a Python helper argument collision;
  corrected before creating the workflows. Initial sandbox checks also failed
  on temporary-directory/process restrictions. Repeating only the focused
  tests with permitted process access passed.
- The original combined protocol/federation run returned exit 125 with an
  incorrect timeout flag. Independent review identified the cleanup reporting
  gap; the runner now preserves `timed_out: true` even if tree or final cleanup
  fails. Direct-child reap is attempted in all timeout paths.
- Separating groups exposed that `tests/vectors` contains fixtures rather than
  pytest tests (exit 5). Removed the empty standalone invocation; protocol
  vector tests and both regeneration checks remain.
- The federation group displayed failures and reached its unchanged 90-second
  local bound, returning exit 125 / `timed_out: true`. The isolated first
  failure was `test_core_v02_baseline_accepts_exact_110_artifact_inventory`:
  existing test code calls `git hash-object` on dirty source, then `git cat-file`
  for unstored blob `19a68a9b634722c5253380f6b69ae9be609199d7`, the current
  dirty `quinn_adapter.rs` hash. No Git objects were manufactured, tests weakened,
  or dirty work reverted. The full federation group remains a clean-checkout
  Linux CI gate; its hosted outcome is unverified. Further failures may exist.
- Cleanup inspection after this timeout found no surviving matching test/runner
  process. Free disk was **14.26 GiB**, down less than 0.1 GiB from pre-check
  inspection. No containers or infrastructure were started.
- No local rerun of the full Go/Rust CI profiles or OPA installation was made.
  Earlier transport checks are recorded separately in the overnight report and
  do not substitute for an execution of the new hosted matrix.

## Review and publication status

Independent read-only review examined permissions, cache writes, shell inputs,
cross-platform commands, artifacts and timeout cleanup. Its cleanup findings
were addressed with regression coverage. It also corrected the documentation's
overbroad exclusion claim: federation documentation assertions are included.

Action pins were resolved against official release commits. The OPA checksum
was read from the official release's checksum text; no local binary was
downloaded. Workflow JSON parses and selected security contracts pass, but
GitHub schema acceptance, Linux execution, hosted toolchain availability,
complete Go/Rust/OPA outcomes, duration and billing remain unverified until a
published run. The existing remote branch requires separately authorized
protection/signature bypass for a new unsigned commit; prior approval applied
only to `8e548588`.
