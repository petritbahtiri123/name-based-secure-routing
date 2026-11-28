# NBSR agent guidance

Start with the current task's verified checkout and authority. Use the
[handoff template](docs/agents/HANDOFF.md) before transferring work; a checkout
name or old checkpoint does not identify the active experiment owner.

## Read only the relevant area

The durable rules below apply to every task. Before changing an area, read its
applicable requirements in [area guidance](docs/agents/AREA_GUIDANCE.md), using
the matching heading. Paths in that document are repository-root-relative.
Do not load unrelated histories or evidence archives for orientation.

| Area | First focused check or reference | Required context |
| --- | --- | --- |
| SPHERE pacing | Focused checks in the existing methodology | [SPHERE paced diagnostics](docs/benchmarks/SPHERE_PACED_2026-10-19.md) |
| Lifecycle/admission | `tests/performance/test_b3_accept_window.py`, `tests/performance/test_linux_native_lifecycle.py`; commands below | [Admission](docs/benchmarks/B3_ACCEPT_WINDOW_DIAGNOSTIC.md), [close diagnosis](docs/benchmarks/B3_CLOSE_REASON_DIAGNOSTIC.md) |
| Connector mock model | `tests/test_connector_control_model.py` and named neighbors | [Area guidance: Project CI](docs/agents/AREA_GUIDANCE.md#project-ci) |
| Offline connector configuration | `deploy/single-instance/test_validate_config.py` and connector neighbors | [Area guidance: Single-instance offline configuration](docs/agents/AREA_GUIDANCE.md#single-instance-offline-configuration) |
| Development Go/Rust connector | Focused commands in `interop/nbsr-go-peer/connector/README.md` | [Area guidance: Connector development-only Go/Rust slice](docs/agents/AREA_GUIDANCE.md#connector-development-only-gorust-slice) |
| CI profiles | `docs/CI.md` and the affected `tests/ci/` contracts | [Area guidance: Project CI](docs/agents/AREA_GUIDANCE.md#project-ci) |
| Federation/registration/authority fixtures | Exact tests and neighbors under the matching area-guidance heading | [Area guidance](docs/agents/AREA_GUIDANCE.md); preserve historical pins and fixture-only limits |

Some tracked references may be absent in a sparse checkout. Check exact tracked
paths and skip-worktree flags before treating absence as a broken reference; do
not restore files or change sparse settings merely to follow this table.

These are navigation aids, not execution authorization. Verify the environment,
cache, command effects and resource bounds below before running any check.

## Scope and working method

- Follow the current task's authorization. This file does not authorize publication,
  infrastructure activation, dependency downloads, or security-setting changes.
- Inspect `git status --short` and `git branch --show-current` before editing.
  Preserve unrelated tracked and untracked work. Never use broad cleanup or staging.
- Work sequentially on the smallest evidenced problem. Start with relevant source,
  tests and the current evidence record; expand context only to resolve a specific gap.
- Add a focused regression for behavior changes, inspect the diff, and perform one
  scoped correctness/security review. Do not repeat expensive checks without a reason.
- Before every push, include the change's relevant tests in the applicable CI
  workflow/profile and verify that CI selects and collects them. Add or update
  CI wiring in the same change when needed; do not defer it to a separate CI task.
  Record the selection/collection check and actual test results in the handoff;
  an unexecuted check is not a pass. Preserve existing execution/resource gates.
- Keep diagnosis, implementation, measured results and hypotheses distinct. Report
  failed checks and incomplete validation. Commit, push and merge need task authority.

## Architecture and sources of truth

For direction, scope, milestone or readiness decisions, start with the
[project direction guide](docs/architecture/project-direction.md), then read the
linked authoritative sections and current evidence for the affected area. Reuse
context already checked in the task; routine small edits do not require rereading
the whole architecture or roadmap. The guide does not replace frozen contracts
or grant execution authority.

- `README.md` and `CONTRIBUTING.md`: overview, setup and contribution checks.
- `docs/architecture/NBSR_Protocol_Vision_V3.6.md`: architectural direction;
  `docs/protocol/status.md`: implementation and evidence scope. Read only relevant
  sections and verify status claims against code and retained evidence.
- `docs/protocol/`: frozen protocol decisions and terminology. Do not rewrite an
  approved contract, weaken authentication, or add fallback to make a test pass.
- `crates/nbsr-transport/`: Rust/Quinn transport, authentication and session boundaries;
  `src/bin/benchmark_support/`: benchmark-only lifecycle helpers.
- `nbsr/`, `services/`, `gateway/`, `policy/`, `verifiers/`: Python reference behavior,
  service/gateway integration, policy and authorization components.
- `vectors/` and `tests/`: deterministic protocol artifacts and regression coverage.
- `scripts/performance/`, `tests/performance/`, `docs/benchmarks/` and
  `evidence/performance/`: benchmark execution, validation, methodology and evidence.
  For admission work start with `docs/benchmarks/B3_ACCEPT_WINDOW_DIAGNOSTIC.md`;
  for close diagnosis use `docs/benchmarks/B3_CLOSE_REASON_DIAGNOSTIC.md`.

## Setup and focused checks

Run commands from the repository root using an existing provisioned environment.
Check `pyproject.toml`, `constraints/dev.txt`, `constraints/runtime.txt` and the
crate's `Cargo.toml`/`Cargo.lock`. Rust uses edition 2024. Verify installed tools
and cache locations before building; do not silently install a toolchain.

Python metadata permits `>=3.12,<3.15`. README distinguishes recorded 3.12/3.13
test coverage from permitted 3.14. A focused check does not establish a fully
tested version matrix; preserve that distinction when reporting validation.

For an explicitly authorized fresh Python setup, the repository's documented command is:

```sh
python -m pip install --constraint constraints/dev.txt -e ".[dev]"
```

For the lifecycle/admission area, focused checks are:

```sh
python -m pytest -q -p no:cacheprovider tests/performance/test_b3_accept_window.py tests/performance/test_linux_native_lifecycle.py
python -m ruff check --no-cache scripts/run_b3_v2.py
cargo test --locked --offline --manifest-path crates/nbsr-transport/Cargo.toml --features benchmark-harness --jobs 2 --test handshake
cargo fmt --manifest-path crates/nbsr-transport/Cargo.toml --check
```

Before Cargo commands, set `CARGO_TARGET_DIR` to the existing verified cache for
that platform. Reuse cached dependencies; an offline cache miss is not permission
to download. Run the exact regression first, then relevant neighboring checks.
`CONTRIBUTING.md` lists broader Python/Rust and vector checks for changes that need
those gates; do not run every repository-wide or deployment check for a small fix.
Demo/bootstrap scripts can regenerate credentials and start/build infrastructure;
read their effects and confirm they are within the task before running them.

## Bounded local experiments and evidence

- On constrained development machines, default to at most two build jobs. Require
  at least 8 GiB free before a build; stop below 6 GiB or after 2 GiB disk growth.
- Bound each build/trial to 120 seconds including cleanup, stopping work by
  95-105 seconds. Use a supervisor that terminates the owned process tree/container,
  preserves logs and verifies cleanup. Never extend a failed run silently.
- Use a small controlled regression and a 16-client paired check before a justified
  larger run. Record every changed workload parameter and keep before/after tests
  otherwise identical. Explicit one-slot admission remains a comparison control.
- For slow host evidence collection, the lifecycle coordinator has an opt-in
  `--archive-collection` mode. See `docs/benchmarks/NATIVE_ARCHIVE_COLLECTION.md`;
  keep full archive inventories and the original live/offline outcomes distinct.
- Retain exact commit plus dirty-patch/source and binary hashes, commands, fixture
  identity, limits, result cardinality, failure markers and ownership counters.
  A base commit alone does not identify binaries built from uncommitted changes.
- Never weaken validators, discard failed attempts, substitute zero cleanup counts,
  or confuse handshake/admission failures with later close/ACK failures.
- A single-host Docker pass does not prove multi-host/WAN behavior, sustainable
  capacity, maximum throughput or production readiness. A 16-client pass does not
  establish a 4096-client fix. More admission slots are not a capacity guarantee.
- Read archive indexes/manifests and selected entries; preserve archives and avoid
  bulk extraction. Machine-specific restore indexes and task checkpoints can be
  outside this checkout: locate them from the task and verify their current state.
- Clean up only resources created by the task. Preserve existing images, volumes,
  caches and unrelated containers. Do not publish private keys, tokens or raw secrets.

## SPHERE SSH from the connected laptop

- Use the existing Windows OpenSSH aliases: `ssh nbsr-client` and
  `ssh nbsr-server`. Inspect the current user SSH config first; these aliases
  already route through `nbsr-xdc` and `sphere-jump`. Do not remove ProxyJump
  or assume the private VM addresses are directly reachable from Windows.
- Run from the connected laptop, not the cloud workspace. A successful Jupyter
  login does not establish workstation SSH or CLI authentication. Start with a
  bounded read-only hostname check using the existing identity and host-key checks.
- For authorized administrative work after logging into the test VM, use
  `sudo -i` (lowercase i). This does not authorize security-setting changes.
- If SSH fails, preserve the exact error and execution environment. Distinguish
  socket/connect failures from authentication failures and tool denials; do not
  bypass a denial, regenerate credentials, or alter network settings as a retry.
- Reachability and a generic process-name scan do not prove prior run cleanup.
  Verify the exact run receipts/process identities before another measured run.
  Do not overlap live dashboard collection with measurement until its transport
  and resource overhead satisfy the existing measurement gates.

## Maintain this guidance with the change

When a change alters setup/test commands, repository layout, verified workflows,
resource limits or evidence interpretation, update the relevant `AGENTS.md` and
related documentation in the same change. Verify referenced paths and commands;
state validation limits instead of claiming unrun success. Preserve useful nested
guidance and historical negative evidence.

When a milestone or its evidence boundary changes, update the affected status
record and the direction guide's milestone/source pointers in the same change.
Keep historical results and approval records intact; link the scoped successor
evidence and record remaining gates rather than promoting a fixture to readiness.

Keep durable rules here. Put transient run IDs, current worktree status and test
counts in an evidence record or task checkpoint, not routine edits to this file.
Review guidance relevance before finishing; do not rewrite it when nothing changed.
This is a per-change maintenance workflow, not a scheduled task.

Project `.codex` settings are not required for this guidance. Do not modify global
instructions, model settings, approval/sandbox/network permissions or credentials
as part of documentation upkeep. Codex loading behavior is described in the
[official AGENTS.md guide](https://developers.openai.com/codex/guides/agents-md/);
other agents may need explicit loading and have different instruction precedence.

## Isolated connector Docker fixture

The connector's opt-in Docker restart fixture is documented in
`interop/nbsr-go-peer/connector/README.md`. Only that isolated test mode permits
an explicitly pinned private IPv4 endpoint instead of loopback. Keep Docker
logging disabled for private fixture pipes, retain exact synthetic bindings,
require scenario-specific cleanup evidence before confirmation, and preserve all
existing resource guards. It does not activate runtime trust or READY.
For `--first-stop kill`, preserve the exit-137/PID-zero/no-OOM and removed-network-
endpoint checks. Never substitute a graceful Go cleanup marker after SIGKILL;
Gateway must retain the exact owner/ticket until distinct supervisor confirmation.
The `--first-stop network` variant changes only the trial Connector's attachment
to its trial network. Require unchanged process identity through disconnect/connect;
restored connectivity alone must not confirm cleanup or imply registration recovery.
For `--first-stop auto-network`, both local coordinator/socket cleanup and exact
Gateway ticket confirmation must precede the next fixture/session. The private
prior-session receipt is synthetic test IPC only; require unchanged Connector PID
and StartedAt across recovery and retain the default coordinator's no-reuse rule.
Automatic fixture runs allow at most five cycles/six sessions. Preserve each
cycle's ownership/receipt evidence and the existing 120-second cleanup-inclusive
bound; do not silently extend runtime or infer unbounded recovery from this trial.

## Local Demo Lab

The separate P1 two-relay fixture is documented in
`docs/demo/p1-cross-gateway-telemetry.md`. Its explicit command is
`python scripts/demo/cross_gateway_telemetry.py`; focused tests are
`tests/demo/test_cross_gateway_telemetry.py` with `tests/test_name_relay.py`.
It opens only task-owned ephemeral loopback listeners and creates temporary
encrypted test-key files. Keep the 45-second cancellation deadline plus bounded
8-second cleanup (53 seconds total), real service-side
counts and closed public trace fields. Keep trace IDs local to each component;
only the test collector joins observations, with no on-wire trace identifier.
Each gateway runs in its own supervised subprocess; verify distinct identities,
zero remaining resources and reaped exits before success. It is a live Python
relay fixture, not a Core/Federation or production gateway claim. Do not
wire it to either Lab, VMs or benchmark controllers, or rewrite historical demo
evidence. Missing/failed cleanup must remain unconfirmed.
Always attempt gateway shutdown/reaping in `finally` even when client TLS close
fails or is cancelled; bound that close and preserve the failed trial outcome.
`--format terminal` presents measured public results in colored boxes. Interactive
output defaults to this view; redirected output and `--format json` remain raw
JSON. Keep expected policy/connect rejection visually distinct from a failed
test, and never expose private IPC diagnostics.

For `tools/demo-lab` and its setup/launcher wrappers, read
[Local Demo Lab guidance](docs/agents/AREA_GUIDANCE.md#local-demo-lab).
Historical demo verification pins remain separate from current-source receipts.

The read-only Demo Lab `status` command inventories recovery markers only;
absence never establishes cleanup, liveness or readiness. Preserve marker contents
and reconcile owners before restart. See the focused status checks in area guidance.

Dashboard lifecycle failures must attempt owned coordinator and HTTP socket cleanup;
socket closure alone never establishes scenario cleanup or permits lock removal.
Close the dashboard listener before potentially slow coordinator cleanup; preserve
cleanup attempts and uncertainty even when either operation fails.
A worker surviving the shutdown join must report cleanup uncertainty and retain UI
ownership for reconciliation; do not equate launcher failure with process exit.
A failed or interrupted shutdown join/worker inspection also leaves cleanup
unconfirmed; retain ownership and preserve the original failure for diagnosis.
Dashboard cleanup joins share one monotonic budget; expiry-thread survival or
inspection failure retains UI ownership. A wait budget is not a process-exit guarantee.
Track HTTP shutdown helpers before start and inspect all within the shared cleanup
budget; any surviving or uninspectable helper keeps UI ownership unresolved.
Permit at most one retained HTTP shutdown-helper attempt per server session;
reject repeats without discarding ownership, including after a failed start.

The isolated Docker harness `--cleanup-failure` option requires one auto-network
cycle. It injects a synthetic Gateway cleanup callback error, retains ownership
through explicit retry, rejects the stale ticket and withholds the next fixture
until exact successful confirmation. Preserve the bounded failed/retry-pending
observations; this is not evidence of a real backend cleanup failure.
