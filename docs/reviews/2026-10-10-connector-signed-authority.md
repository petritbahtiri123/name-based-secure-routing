# Offline signed registration authority checkpoint — 2026-10-10

The explicitly selected development profile now verifies signed genesis key,
ownership and delegation fixtures through existing Federation COSE validators.
Action 24576 is accepted only with the exact development profile and explicit
record-digest/signer inventory. No frozen allocation or runtime provider changed.

The adapter binds principal/service/gateway/policy pins, the actual peer key,
complete dependencies, request bytes, connection/session/counter and current
revision. A bounded single current receipt requires instance-local issuance
identity; a bare/reconstructed dataclass is rejected. Signature purpose, chain
ancestry, scope narrowing, signed validity, signer validity and fixture freshness
are checked. The exclusive eligibility ceiling is their minimum; renewal cannot
extend it. This does not implement previous-accept ownership or application-work
grace; those remain coordinator responsibilities.

Review exposed logical-clock rollback after a successful later observation or a
failed expiry check. Two deterministic regressions failed before the minimal
observed-time-floor fix and pass afterward. Revision changes cannot reset it.
This is serialized fixture time, not a real clock or timer implementation.

## Validation and retained failures

- Final scoped Python suite: **444 passed, 5 deselected, zero failed** in 4.50s
  (6.44s supervised). Includes all 43 adapter tests and selected existing COSE,
  key authorization, delegation/ownership, connector and CBOR/vector neighbors.
- Five tests that call random key generation were explicitly deselected. Exact
  names and full command are retained in `signed-authority-neighbors.json`.
  Only existing public deterministic test-key material signed in-memory fixtures.
- Focused milestones: 24, then 41, then 43 passes. Initial missing-module red
  (exit 2) and two clock regressions red (exit 1) are retained, not hidden.
- Initial direct Ruff check found 22 E701/E702 style diagnostics; formatting
  fixed them. Final supervised Ruff lint/format pass. Initial direct diagnostics
  were tool-visible but not separately archived. `git diff --check` passes.
- Independent scoped rereview found no remaining blocking findings; reviewer
  did not independently rerun tests. Review and all nine supervised run records,
  stdout/stderr, final source snapshots and supervisor sources are retained.
- Python 3.14.6, pytest 8.4.2, cryptography 45.0.7, Ruff 0.11.13. This permitted
  local Python version is not evidence for README's full tested-version matrix.

## Evidence scope and remaining gates

Signer trust, digest inventory, freshness provenance and denial revisions are
explicit local fixtures. Real signatures do not authenticate their provenance.
Genesis records only; no recovery/transition trust is inferred. Instance-local
receipt identity is not a hostile-process boundary or portable authenticated
receipt. Denials are cumulative offline snapshots, not verified event delivery.
No threshold-evidence bypass, private token, revocation receipt producer, live
coordinator integration, keys generated, sockets, downloads or credentials files.
No real timers, runtime revocation delivery, authority discovery or Stage 3
closure. Stage 3 remains partial; stages 1-2 remain 2/10 complete.

Each supervised run had 95s work/120s cleanup bounds, offline settings and two
build-job limit, >=8GiB disk start and 2GiB RAM reserve (stricter 256MiB disk-growth
guard). No resource abort occurred; all direct children were reaped. Final
read-only check found no visible Python/Cargo/rustc/Go workers. No containers or
sockets were created in this slice. No commit, staging or push. Existing dirty
work and historical manifests remain preserved. See JSON for exact HEAD, source,
dependency and evidence hashes; HEAD alone does not identify dirty sources.
