# Challenge revision consistency — overnight 2026-10-11

Python Coordinator.prove accepted a newly verified revision even when it differed
from the revision captured in the pending challenge. Rust's existing development
coordinator already rejects this mismatch. The approved expectedRevision commit
boundary requires a fresh exchange rather than carrying a challenge across it.

Two deterministic registration/renewal regressions failed before the two-line
RECORD_STALE guard and pass afterward. The proof consumes the challenge; no owner
or lease changes occur, and the next operation counter can start a fresh exchange.
This does not invalidate unrelated active work or add a new lifetime policy.

Validation: focused red 2 failed/103 deselected; green 2 passed/103 deselected;
final neighbors **434 passed, zero skipped/deselected/failed** (2.96s pytest,
4.22s supervised). Python generator --check matches20 files/24 scenario specs;
Node verifies19 artifact hashes and34 replay-cache transitions over4 traces.
These are byte/model checks, not additional live interoperability results.
Ruff lint/format and git diff --check pass. Independent review clear, no rerun.
All seven supervised runs retained, including red. Exact commands, source
preimages/final snapshots, incremental patches and hashes are in the JSON.

AGENTS.md now records the challenge/current revision distinction. Historical
reports/manifests were not refreshed; their hashes identify their own snapshots.
No Rust source changed or Rust test rerun claimed. No allocation, trust producer,
threshold receipt, key generation, network, build or live activation. Stage3
partial, stages1-2 2/10. All work stays uncommitted/unpublished; index empty.

Runs used provisioned Python3.14.6 and Node, offline/two-job supervisor settings,
95s work/120s cleanup bounds, >=8GiB disk start/6GiB floor, stricter256MiB growth
and2GiB RAM reserve. No resource abort; all direct children reaped. Final process
check found no Python/Cargo/rustc/Go workers. No task sockets/containers created.
