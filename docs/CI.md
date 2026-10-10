# Project CI

The quick workflow checks pushes to `codex/nbsr-v3-wp0-wp1`, pull requests,
and manual dispatches. It does not deploy or run live connection benchmarks.
The separate extended workflow is manual only; there is no overnight schedule.
Both files use JSON syntax, which is valid YAML and can be inspected offline
without installing a YAML parser.

## Coverage and limits

| Job | Platforms | Checks |
| --- | --- | --- |
| Python | Ubuntu 24.04, Windows 2025 | Explicit runtime, gateway, security, admission and CI tests; `pip check` |
| Python protocol | Ubuntu 24.04 | Protocol, vectors and federation tests except independent wire-peer builds; deterministic vector regeneration; privacy check; correctness lint |
| Rust | Ubuntu 24.04, Windows 2025 | Format, default library check, benchmark-feature library, handshake/credit/drain/config, frame codec, doc-tests, all-target Clippy |
| Go | Ubuntu 24.04, Windows 2025 | Test and vet all five modules, including the nested client demo and ISP adapter |
| Node and policy | Ubuntu 24.04 | Core/federation independent verifier tests and vectors, exporter vectors, OPA policy tests |
| Manual extended | Ubuntu 24.04 | All nonignored Rust integration tests, or the existing ignored replay-history soak |

Python uses 3.13.14, Rust 1.97.1, Go 1.26.5 and Node 24.19.0. These are explicit
pins, not a claim of coverage for every version allowed by package metadata.
OPA 1.4.2 matches the repository policy runtime; its official static binary is
verified against a pinned SHA-256 before execution. Node packages currently
have no dependencies, so there is no npm installation.

Python installation uses `constraints/dev.txt`; Cargo fetch uses `--locked`
and tests use `--offline`; Go resolves recorded module versions, verifies its
module cache, and tests with `-mod=readonly` and `GOPROXY=off`. Lockfile diffs
fail their jobs. The Rust default-feature library check complements the
benchmark-feature suite; it is not an exhaustive feature matrix.

Quick checks intentionally exclude independent multi-language live-wire builds,
root-level historical documentation assertions, broad performance harness runs, Docker/Kind,
network capture, infrastructure startup and capacity trials. Manual extended
Rust includes more lifecycle tests but does not establish WAN or throughput
results. Federation documentation/baseline assertions are included. Full repository Ruff style/format cleanliness is not claimed: existing
Python receives the critical `E9,F63,F7,F82` gate, and new CI code gets full Ruff.

## Execution and security

All jobs run on GitHub-hosted runners with read-only `contents` permission.
Checkout does not persist credentials. Actions are pinned to full commit SHAs;
there are no secrets, deployment environments, privileged PR events or
self-hosted runners. PR code still executes as untrusted code in the disposable
hosted runner. No test job should be given repository or infrastructure secrets.

Dependency-only caches use OS/toolchain/lockfile keys. Saves occur only after a
successful push to the development branch, never from a PR or manual run.
Workspaces, compiled targets, credentials and fixtures are not cached. Failure
artifacts contain only command labels, exit codes and timeout flags, retained
for seven days; command output remains in the normal Actions log. Installation
failures can occur before an outcome file exists, so inspect the failed step.
Do not add raw environment dumps, tokens, packet captures or private fixtures.

Concurrency cancels superseded runs for the same workflow/ref. Quick runs have
seven jobs: two Python (20 minutes each), two Rust (25 each), two Go (20 each),
and one Node/policy (10). The configured upper bound is 140 aggregate runner
minutes before cancellation/overheads, not an observed duration or price.
Actual billing depends on GitHub's repository/account plan and runner rates.
Cold dependency setup may be slower; caches avoid repeated downloads but do not
cache compiled results. Rust/Go use two build workers, Rust two test threads.
Commands have explicit timeouts (90–600 seconds quick, 1200 manual), with
process-tree termination on timeout; manual jobs have a 30-minute ceiling.
No hosted duration or cost has yet been measured for this implementation.

## Local use and troubleshooting

```text
python scripts/ci/check.py validate
python scripts/ci/check.py python-core --list
python -m pytest -q -p no:cacheprovider tests/ci
python -m ruff check --no-cache scripts/ci tests/ci
```

Profiles are `python-core`, `python-protocol`, `rust`, `go`, `node`,
`rust-extended` and `soak`. Local commands default to 90 seconds each; larger
timeouts are reserved for hosted CI. This runner does not install dependencies
or enforce the laptop's disk/RAM guards: local build/test supervision must still
follow `AGENTS.md`. Set the verified `CARGO_TARGET_DIR` and offline Go/Cargo
environment before any local build; never turn an offline miss into a download.
Do not run a whole profile locally if its cumulative time exceeds the authorized
cleanup-inclusive trial budget; invoke the listed commands in bounded groups.

Exit 124 means timeout with tree termination attempted successfully. Exit 125
with `timed_out: true` means tree cleanup failed and requires inspection, even
if the direct child was reaped. Exit 125 without a timeout means startup or
runner failure. Other nonzero codes are the command's failure. A timeout is
not permission to enlarge the budget or discard the result.

For dependency failures, inspect the pinned version and lockfile rather than
updating dependencies automatically. For Windows failures, compare the same
profile on Linux and inspect path, permission and socket assumptions. On an
unpublished workflow branch, manual dispatch may not be listed until GitHub
knows the workflow on its default branch; do not change the default branch or
protection to work around that. Hosted runs and their logs are the final check
of Actions schema, toolchain availability and cross-platform execution.

The structural validator checks selected security contracts, not GitHub's full
workflow schema. Local Windows checks cannot establish Linux success. CI status
is pending until a published commit has actual workflow/check results; an empty
check list is not a pass.

## Release boundary

Versioned binaries and Docker images, single-instance/Kubernetes installation,
and a device Go client are future product goals. These workflows only build
and test source. Release publication needs a separate reviewed design covering
version/tag authority, reproducible artifacts, provenance/signing, registry
ownership and narrowly scoped publication permissions. It must run from an
explicitly authorized trusted release, never a pull request. No package push,
registry credential, cluster provisioning or device DNS change is configured
or authorized by this CI change. Deployment feasibility is a separate study.

## Sources and pin maintenance

Action release SHAs were resolved from the official `actions/*` repositories
on 2026-10-10: checkout v7.0.1, setup-python v7.0.0, setup-go v7.0.0,
setup-node v7.1.0, cache v6.1.0 and upload-artifact v7.0.2. Review source and
release notes before changing pins, then rerun CI regressions and a hosted run.
See [GitHub secure-use guidance](https://docs.github.com/en/actions/reference/security/secure-use),
[Ubuntu runner inventory](https://github.com/actions/runner-images/blob/main/images/ubuntu/Ubuntu2404-Readme.md),
[Windows runner inventory](https://github.com/actions/runner-images/blob/main/images/windows/Windows2025-Readme.md),
and the [OPA release](https://github.com/open-policy-agent/opa/releases/tag/v1.4.2).
# Approved transport source authority

The current-source gate in `tests/federation/test_baseline_immutability.py` uses
`assert_transport_lifecycle_core_overlay`. Its separately versioned authority is
`docs/protocol/registries/core-v0.2-transport-lifecycle-overlay.json`, recognizing
the reviewed `99ac954e0c0d90a221b42492a59fa4d5b962ea5d` source snapshot.
The original baseline, F75, P1/P2 and ACK authorities remain unchanged. Historical
ACK tests use their approved `94a1e4a` fixture, while the main gate still reads
current canonical source bytes.

The layer checks all 110 legacy artifacts and explicitly pins `owned_send.rs`,
`udp_socket.rs`, `benchmark_bind.rs`, `Cargo.toml` and `Cargo.lock` in the transport
crate. The six verification-source hashes in the approval proposal identify
review evidence; they are not additional runtime protocol gates. This selected
scope is not a complete build dependency closure or production certification.
Future ACK or other changes to pinned files require a new reviewed versioned
authority rather than extending this snapshot's approval silently.

Run focused authority, current-source and historical ACK tests in bounded groups
using the provisioned environment; retain failed attempts and distinguish local
validation from the hosted CI matrix. See the activation checkpoint under
`docs/reviews/2026-10-10-authority-activation.md` for measured results and limits.

Sparse local checkouts may omit committed packet evidence required by federation
tests. Inspect skip-worktree flags, sparse patterns and Git blob availability
before diagnosing missing packaging. Validate exact committed test/evidence bytes
in a temporary materialization when appropriate; preserve the original missing-
input result and do not overwrite user deletions or weaken tests. This scoped
check is not a claim that the incomplete working checkout passes the full suite.

Runner-dependent paths must be initialized at step execution time, for example
through `RUNNER_TEMP` and `GITHUB_ENV`; GitHub does not expose the `runner` context
in job-level `env`. Local contract validation catches this known error but is not
a full hosted schema check. The first published run failed before job creation;
see `docs/reviews/2026-10-10-hosted-ci-d4ca54eb.md` for the preserved result.

Node verification includes a Python vector-generator subprocess and therefore
requires the constrained project runtime, not just a Python executable. The
prepared setup uses `python -m pip install --constraint constraints/runtime.txt
-e .` on the hosted runner. This does not authorize local dependency downloads.
The first executing matrix's three successes and four failures are retained in
`docs/reviews/2026-10-10-hosted-ci-9ac925df.md`; the Node setup correction is still
unpublished, and the Linux diagnostic/fixture and Windows ACL failures remain.

The subsequent local portability patch is documented in
`docs/reviews/2026-10-10-ci-portability.md`. It preserves alias rejection across
filesystem diagnostics, uses the existing platform-specific Go fixture hierarchy,
and replaces the complete ACL only on test-owned enrollment directories. It does
not relax production ACL validation. Native Linux and hosted rerun remain required.
