# Project CI implementation plan

**Goal:** Add bounded, reproducible GitHub Actions checks for the actual Python,
Rust, Go and dependency-free Node components, with no deployment authority.

**Architecture:** A small checked-in command runner defines explicit quick
profiles. GitHub-hosted Linux and Windows jobs install pinned toolchains and
resolve locked dependencies, then execute those profiles. Extended Rust tests
and the existing ignored soak are manual choices only. Workflow files use JSON
syntax (valid YAML) so offline validation needs only Python's standard library.

**Authorization:** The user requested design followed by implementation and
independent review in this session. Local CI commits are authorized; pushing
through branch/signature rules needs fresh approval. The preceding frame-body
test remains a separate, uncommitted scope.

## Decisions and constraints

- Target pushes to `codex/nbsr-v3-wp0-wp1`, all pull requests, and manual dispatch.
  No schedules, `pull_request_target`, privileged `workflow_run` or self-hosted runners.
- Python 3.13 on Linux/Windows; metadata's 3.12 through 3.14 range is not a tested
  CI matrix. Rust 1.97.1, Go 1.26.5, Node 24.19.0 match provisioned tools/contracts.
- Python quick scope: explicit runtime/security files, plus Linux protocol/vector/
  federation tests excluding the independent live-wire build matrix. Historical
  documentation tests and expensive harness/live suites are not silently called quick.
- Rust quick scope: default library check, benchmark-feature library, handshake,
  credit, drain, config and codec tests, doc-tests and all-target Clippy. No ignored soak.
- All five Go modules get test/vet checks on both OSes. Node vector verifiers run
  on Linux without npm installation because their manifests have no dependencies.
- Use two build jobs/workers; hosted cold setup/builds have explicit job/command
  limits. Local validation stays offline and within existing laptop resource guards.
- Pin official actions to verified full commit SHAs. Read-only contents permission,
  no secrets, disabled checkout credentials, no untrusted text in shell scripts.
- Cache dependency downloads only; save caches only on a successful branch push.
  Never cache workspaces, private fixtures, build outputs or test artifacts.
- Upload only generated fixed-schema command outcome JSON on failure, no captured
  test output, credentials, raw fixtures, filesystem paths or environment values.
- Keep live performance, network capture, Docker/Kind deployment and capacity
  experiments outside hosted CI. Manual soak is not a throughput claim.

## Tasks

- [x] Add runner/contract regression tests; demonstrate absence before implementation.
- [x] Implement command profiles, bounded child cleanup and sanitized summaries.
- [x] Implement quick and manual workflows plus offline structural validator.
- [x] Validate focused profiles locally using provisioned caches; do not cold-build.
  See `docs/CI_VALIDATION_2026-10-10.md` for failed federation/timeout attempts and
  unrun hosted, Go/Rust and OPA checks; this is not a full-matrix pass.
- [x] Obtain independent correctness/security review and repair findings.
- [x] Finalize CI usage/troubleshooting and small factual README/AGENTS fixes from
  observed behavior; record unrun hosted checks and scoped documentation findings.
- [ ] Commit CI scope only, preserve the frame-body follow-up and unrelated files;
  report exact commit, limits/cost estimate and fresh bypass approval requirement.

## Review focus

Untrusted PR permissions/cache writes; fixed artifact fields on failing commands;
subprocess tree cleanup at timeout; Windows shell/paths and Unix mode differences;
lockfile immutability and explicitly excluded heavyweight tests. Passing local
contract tests never substitutes for a real GitHub workflow execution.
