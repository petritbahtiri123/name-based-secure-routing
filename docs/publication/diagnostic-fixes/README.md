# Standalone diagnostic fixes and retained history

This collection preserves the standalone benchmark work without treating a local
diagnostic or its historical authorization as a current operational entrypoint.
The original source directory is untouched. `source-map.json` accounts for all
168 top-level files, all 111 Python files including nested build/TLS work, every
original SHA256 and every published source SHA256. Identical originals share one
snapshot: 111 source paths map to 108 physical snapshots. Python import names,
literal file dependencies, test method names and literal pin tables are indexed.
Snapshots have a `.py.snapshot` suffix and are not automatically test-discovered.

## Reusable helpers

The five helper modules and five tests in
`scripts/performance/diagnostic_support/` retain these behaviors:

| Fix | Source | Regression |
| --- | --- | --- |
| Exact absence evidence requires completed command and released ownership; rejects wrong IDs, partial/error output and bool exit codes | `diagnostic_absence.py` | `test_diagnostic_absence.py` (6) |
| Exact image metadata and task-label separation, digest-bound profile loading | `diagnostic_labels.py` | `test_diagnostic_labels.py` (6); synthetic public profile replaces local image metadata |
| Bounded dirty-source reporting only from authenticated inventory; mode/byte differences remain rejected, aliases and sensitive paths blocked | two unmodified functions from `public-probe-metadata-candidate.py`, extracted as `dirty_source_metadata.py` | eight unit tests derived from `test_probe_dirty_metadata.py`; Git is mocked |
| Python/platform/package preflight precedes imports and preserves original integrity rejection | `runtime_preflight.py` | `test_runtime_preflight.py` (6) |
| Bound archive inventory, bytes, modes and file types without extraction | `source_presentation_contract.py` | `test_source_presentation_contract.py` (5) |

Run from the repository root:

```text
python -m unittest discover -s scripts/performance/diagnostic_support -p "test_*.py" -v
```

All 31 tests passed on Python 3.14.6 in this publication review. The metadata helper
preserves the original explicit `/repo` Git scope: it is reusable for that
authenticated container layout, not an arbitrary-host repository scanner. Callers
must authenticate the inventory and supply the checked-byte reader. A synthetic
label fixture tests the same rules without claiming historical image acceptance.
No native operation, real Git subprocess, credential generation or network was
performed by these tests.

## Preserved functional variants

| Fix family | Implementation snapshots | Test snapshots / boundary |
| --- | --- | --- |
| Uncertain creation reconciliation; shared absolute work/cleanup deadlines; retained failed-close ownership | `diagnostic_reconciliation.py`, `diagnostic_*budget*.py`, `candidate_probe_budget.py` | `test_create_reconciliation.py`, `test_cleanup_budget_spec.py`, `test_probe_budget.py`, `test_candidate_budget.py`, all `test_source_budget*` |
| Reviewed payload-only extended probe allocation and full command-chain binding | `public-probe-candidate.py`, `diagnostic_probe_budget.py`, attempts 05–08 | `test_probe_call_chain.py`, `test_git_exception_attempt04.py`; historical runtime and build inputs required |
| Dirty-status reporting refinement | `public-probe-status-candidate.py`, `public-probe-metadata-candidate.py` | `test_probe_status_reporting.py`, `test_probe_dirty_metadata.py`; earlier status-preview behavior preserved as history, latest private-path omission selected for helper |
| Fresh source-volume ownership; no retry after uncertain create; non-force remove plus exact absence | `diagnostic_source_lifecycle.py`, `_v2.py`, `_v3.py` | corresponding `test_source_lifecycle*`; v3's 11 fake-command tests passed in this review |
| Source archive presentation, staged payload binding, source/runtime phases and exact controller/observed mount map | `source_stage_payload.py`, `source_runtime_payload.py`, `source_attempt09*`, `source_attempt10*` | `test_source_payloads.py`, `test_source_binding_v3.py`, `test_source_orchestration*`, `test_source_profile_v3.py`, `test_source10_mapping.py` |
| Runtime dependency candidate and offline Debian closure/install/build supervision | `candidate_probe*`, `debian_*`, all Python sources below `debian-closure-plan/` | `test_candidate_budget.py`, nested `test_activation.py`, `test_build_supervisor.py`, `test_plan_checkpoint.py`, `test_runtime_profile*`, `test_offline_install_v3.py` |
| Single-container two-role adaptation, precredential gates, containment and TLS payload binding | `diagnostic_tls*`, `tls_trial01*`, Python sources below `tls-proof-authorization/` | nested `test_fixture_projection.py`, `test_integration_prerequisites.py`, `test_precredential_gates.py`, `test_single_container_adapter.py`, `test_trial_payloads.py` |

The four offline installer tests also passed: they AST-extract only
`install_debian_files` and replace `subprocess.run` with a mock. The module itself
was never imported or executed. Together with the 11 volume tests, these are 15
additional archive regressions. To reproduce, materialize only their four mapped
snapshots into a new test directory under their original Python basenames, put
that directory and this repository on `sys.path`, and discover the two test
modules. Do not execute the installer module or broadly discover historical tests.
All 108 snapshots were syntax-parsed and checked against their outgoing hashes.

## Exact portability limits

The supervisor variants explicitly require a historical absolute support root
under `nbsr-runtime-47d2ae4-v5/repo/scripts/performance`, plus exact source hashes.
The original common supervisor pins include:

| Module | Historical SHA256 |
| --- | --- |
| `windows_docker_provisioning` | `e22c18ea76a34333f282612e367ff57c12732ffebd8ec2aaaaea86688955aca5` |
| `windows_native_management` | `e89d236476db0367ea45ac56d643e23ed3cef0eab0344f2e7bbf63689c8892f5` |
| `windows_job_backend` | `dc7c955c3159c4182b98eeb717ce27a9798409542d97f6f5c248afacffd3d1af` |
| `process_cancellation` | `29adfd385bfdf9d51304269e576bed71fbd9cb3885653a5de50085549079107c` |

Each variant's actual pin table and dependencies are in the machine-readable map;
later variant pins can differ. Other checks bind exact profile wire digests,
runtime payload bytes, manifests, Git metadata, image identities, finite configs,
staging archives, and build outputs. Those gates were not retargeted or bypassed.
Replacing a local username with `PUBLIC_USER` makes a snapshot explicitly
non-operational and can invalidate payload hashes. It is documentation of the
reviewed logic, not a newly authorized pin set. Modern production supervisor
changes elsewhere in this publication do not validate these historical pins.

## Historical outcomes and exclusions

Historical integration red tests caught missing cleanup behavior and clock-state
latching; intermediate green attempts still failed before the recorded 46-test
historical integration pass. Probe-budget records distinguish initial failures
from reviewed offline proposals without a live retry. Source lifecycle initially
stopped at exact-name volume-list timeout before creation. A later source retry
staged successfully but stopped on missing `cryptography`, with cleanup recorded
as confirmed. Candidate inspection was explicitly not runtime acceptance.
The first source10 run failed exact bind-source comparison; its successor recorded
`PUBLIC_SOURCE_DIAGNOSTIC_PASS_CLEANUP_CONFIRMED` using exact mappings. That record
was not a two-stream TLS proof or a throughput/production result. These are
summaries of retained source records, not live results reproduced here.

Raw console/test logs, local inventory/proposal/result records, six raw patches,
the 440-file staging tar and historical dependency lock are excluded from this
publication. Every top-level item has an individual hash and disposition. No
Python implementation or regression file was excluded as a mere diagnostic.
Nested package caches, images, wheels, Debian packages, local runtime evidence,
authorization records, and credential/config payloads are not copied. Only nested
Python source is retained, with no credential material or private key files read.
Raw patch context is not published; the source variants retain the functional
history. Local source roots are generalized, source/image pins and ownership,
deadline, absence, clean-source and fail-closed checks are preserved.

The remaining historical suites require their exact pinned runtime and fixtures
and are unexecuted. No live containment, Docker behavior, source10 pass, TLS proof,
download/install/build or VM/SSH operation is claimed by this review.
