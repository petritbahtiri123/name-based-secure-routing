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

## Clean committed-tree diagnosis (follow-up)

Tested the exact CI commit `f6400959e93f32f3eec32372c60773c115344583`
in a standalone temporary Git checkout with its own metadata and read-only
alternate access to existing Git objects. No source worktree registration,
pruning, permission change, network fetch, or source-file reset was performed.

The managed-worktree tool was unavailable for this task. The first standalone
setup failed because Windows text writing added CRLF to the alternate-object
pointer; correcting that task-owned pointer to LF resolved object lookup.
The initial full checkout then hit the **2 GiB disk-growth guard at 18.62 s**
and its owned process tree was terminated. Historical performance evidence
accounts for 1367.1 MiB of Git blobs. The installed LFS filter additionally
materialized 43 objects (1,176,576,502 bytes), all present in the existing source
LFS cache. The partial checkout and logs were retained, not deleted or resumed.

A new sparse checkout excluded only `evidence/performance/`, retained the
federation source/tests/vectors/relevant evidence, and set `GIT_LFS_SKIP_SMUDGE=1`
for the process. It completed in **3.22 s**, using **21,970,944 bytes** additional
disk, under a tighter **256 MiB growth guard**. Its HEAD is exactly `f6400959`;
`git status --short` was empty before and after tests. Python imported `nbsr`
from this isolated checkout. No performance archive is needed by the tests run.

Commands below ran with provisioned Python 3.14.6, two-worker environment limits,
offline Cargo/Go settings, a 95-second work cutoff, 120-second cleanup-inclusive
ceiling, at least 8 GiB disk initially and a 2 GiB RAM reserve. Full stdout,
stderr, command/result JSON and cleanup logs are retained locally under the
task's `nbsr-ci-clean-evidence` temporary directory; raw local paths are not
publication artifacts.

```text
python -m pytest -v -p no:cacheprovider --durations=10 tests/federation/test_baseline_immutability.py::test_core_v02_baseline_accepts_exact_110_artifact_inventory
```

**1 failed in 9.66 s**, exit 1; supervisor elapsed **10.63 s**, no timeout or
resource abort. The missing Git blob no longer occurs: clean `quinn_adapter.rs`
resolves to existing Git blob `621275770f05247d64dbe8b3b9481894ed4af01b`.
Instead, the existing authority validator rejects committed `lib.rs`:

```text
CoreBaselineError: modified Core v0.2 parent P1/P2 overlay replacement:
crates/nbsr-transport/src/lib.rs
```

| Value | Frozen P1/P2 authority | Committed file |
| --- | --- | --- |
| Length | 6634 | 6817 |
| SHA-256 | `c3dd27a6b11a53e53f1fcb7cce1b0b3f52c4c616c9c70f07d281d435022c6d3e` | `3db5a0a615e12d4d67ed0380f07e9ad9778bde98a8879817992a0df000f99e43` |

The same `lib.rs` bytes already exist at parent `8e548588`; its most recent
change is `bea16625ab78d2a5404ce02d0c0b5d82e9e6929d`. This is not introduced by
the CI commit or the four uncommitted follow-up files. No authority, protocol
code or validator was changed, and the failing test remains in CI.

```text
python -m pytest -v -p no:cacheprovider --durations=10 tests/ci tests/federation/test_baseline_immutability.py::test_core_v02_baseline_rejects_modified_artifact tests/federation/test_baseline_immutability.py::test_core_v02_baseline_rejects_removed_artifact tests/federation/test_baseline_immutability.py::test_core_v02_baseline_rejects_added_artifact_in_locked_scope tests/federation/test_authorization.py
```

**33 passed in 27.93 s**, exit 0; supervisor elapsed **28.88 s**, no timeout or
resource abort. This comprises 12 CI regressions, three baseline-negative tests
and 18 federation authorization cases. The three Git-heavy baseline tests took
8.53, 8.14 and 8.28 seconds; the positive case took 8.67 seconds in its test call.
Each fixture launches `hash-object` and `cat-file` for 110 artifacts. The demo-ACK
test module repeats the same fixture across many parameterized cases. These
measurements support cumulative fixture cost exceeding the earlier 90-second
whole-group budget, rather than a hang in the isolated failing case. The full
clean federation group was not rerun, so this is not proof that every remaining
case completes or that the hosted 300-second group budget is sufficient.

**Conclusion:** the missing-blob symptom was a dirty-source artifact, but the
federation failure is not solely one: an independent frozen-authority mismatch
is reproducible on the clean committed tree. Resolving that mismatch requires
separately scoped protocol-authority review, outside this CI task. Publishing
is not needed to establish this failure and should not be presented as likely
to produce green CI.

If publication is later authorized, the push triggers seven independent hosted
jobs: Python on Ubuntu/Windows, Rust on Ubuntu/Windows, Go on Ubuntu/Windows,
and Node/OPA on Ubuntu. Python's Ubuntu protocol step includes the known failing
federation test; Windows Python runs the core profile only. Other jobs can still
run, but their outcomes remain unverified. Manual extended Rust/soak does not
run automatically. A published run is still needed for hosted schema/toolchain,
Linux and full matrix verification, after acknowledging or resolving the known
authority blocker; no push or bypass was performed here.

Final cleanup inspection found no matching owned test/Git processes. The four
original uncommitted transport/report files retain their exact pre-check SHA-256
hashes. Both temporary checkouts and all logs remain for review. Free disk was
**12.19 GiB**, free RAM **6.17 GiB**; no container or service was started. This
follow-up modifies only this evidence record and leaves CI implementation at
`f6400959` unchanged.

Independent read-only review confirmed the clean status, source hashes,
pre-existing mismatch and **1 failed / 33 passed** logs. It found no overclaim
in the diagnosis and retained the full-suite/hosted-budget uncertainty.

The subsequent authority investigation is recorded in
[`2026-10-10-ci-authority-decision.md`](reviews/2026-10-10-ci-authority-decision.md).
Four bounded historical/substitution diagnostics passed in 10.97 seconds; the
current-tree positive remains failed. An adjacent two-file candidate is explicitly
inactive and requires an authority decision before implementation. No frozen
hashes, active validators, test selection or CI implementation were changed.
