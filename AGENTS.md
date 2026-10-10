# NBSR agent guidance

## Scope and working method

- Follow the current task's authorization. This file does not authorize publication,
  infrastructure activation, dependency downloads, or security-setting changes.
- Inspect `git status --short` and `git branch --show-current` before editing.
  Preserve unrelated tracked and untracked work. Never use broad cleanup or staging.
- Work sequentially on the smallest evidenced problem. Start with relevant source,
  tests and the current evidence record; expand context only to resolve a specific gap.
- Add a focused regression for behavior changes, inspect the diff, and perform one
  scoped correctness/security review. Do not repeat expensive checks without a reason.
- Keep diagnosis, implementation, measured results and hypotheses distinct. Report
  failed checks and incomplete validation. Commit, push and merge need task authority.

## Architecture and sources of truth

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

Python metadata currently permits `>=3.12,<3.15`, while README describes a narrower
3.12/3.13 tested range. A focused local run on another permitted version does not
establish a fully tested version matrix. Resolve discrepancies with evidence.

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

## Maintain this guidance with the change

When a change alters setup/test commands, repository layout, verified workflows,
resource limits or evidence interpretation, update the relevant `AGENTS.md` and
related documentation in the same change. Verify referenced paths and commands;
state validation limits instead of claiming unrun success. Preserve useful nested
guidance and historical negative evidence.

Keep durable rules here. Put transient run IDs, current worktree status and test
counts in an evidence record or task checkpoint, not routine edits to this file.
Review guidance relevance before finishing; do not rewrite it when nothing changed.
This is a per-change maintenance workflow, not a scheduled task.

Project `.codex` settings are not required for this guidance. Do not modify global
instructions, model settings, approval/sandbox/network permissions or credentials
as part of documentation upkeep. Codex loading behavior is described in the
[official AGENTS.md guide](https://developers.openai.com/codex/guides/agents-md/);
other agents may need explicit loading and have different instruction precedence.

## Project CI

`docs/CI.md` defines the bounded GitHub-hosted profiles in `scripts/ci/check.py`
and the manual extended workflow. Hosted dependency installation does not
authorize local downloads or override the laptop limits above. Run only the
affected profile or command locally with provisioned caches; `--list` inspects
the exact commands without executing them. Workflow security contract tests
are in `tests/ci/`; JSON-syntax YAML permits standard-library validation.
Local structural validation is not evidence of a successful hosted run.

The current-source authority gate uses the separately approved transport lifecycle
overlay: retain the 110-file legacy inventory and its historical ancestors plus
the five explicitly pinned implementation/build dependencies. Test-source hashes
are evidence, not extra runtime gates. Later changes to pinned source require
their own reviewed versioned authority; never refresh an older overlay in place.
Focused regressions are `tests/federation/test_transport_lifecycle_overlay.py`,
`test_baseline_immutability.py` and historical `test_demo_ack_core_overlay.py`
in the same directory. Keep historical fixture checks distinct from the current
source gate; selected-source acceptance is not whole-crate or production proof.
For missing committed evidence in sparse checkouts, inspect skip-worktree flags
and exact Git blobs first. Validate a temporary materialization without restoring
excluded files over user work; retain the original missing-input outcome.

## Large live-bundle harness checks

For explicit 8192 live-bundle support, use the focused boundary tests documented
in `docs/benchmarks/NATIVE_ARCHIVE_COLLECTION.md`. Increased parser/observer
bounds are not permission to run a larger trial: independently verify current
host and guest memory/commit headroom, sustained-pressure aborts, disk guards,
and the authorized cleanup-inclusive runtime. Do not modify host/global network
settings or infer an 8192 capacity result from harness regression success.
