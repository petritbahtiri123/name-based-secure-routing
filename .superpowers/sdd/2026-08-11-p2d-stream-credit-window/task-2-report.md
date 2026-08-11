# P2D Task 2 report: compact credit lifecycle and atomic session admission

## Scope and baseline

- Branch: `codex/nbsr-perf-p2d-stream-credit-window`.
- Required base: `366bbfcfdf5aba9155b476e935f40356eb5fbefa` plus the three committed Task 1 commits through `ba7a5504b6ea8986be7f9525d24731aec36020a8`.
- Implemented compact `nbsr-stream-credit-1` window/refill/consume state, session-owned profile/generation authority, ordinary application-stream registration, P1F replay-history retention, and channel/session cleanup.
- `admission.rs` is a minimal scoped extension used only to expose the registry-owned generation and live grant-expiry authority to `ControlSession`; `session_tests.rs` contains the live session-bound regression.
- No Core v0.1 wire bytes or numeric meanings, RouteGrant schemas, payload behavior, prior evidence, design/plan documents, protected refs, or remote refs were changed.

## Literal RED

Tests were added before the Task 2 implementation for the required window lifecycle, generation ownership, and credited stream preparation APIs.

Command from `crates/nbsr-transport`, with `CARGO_TARGET_DIR=C:\Users\bajra\.codex\targets\nbsr-p2d-task2`:

```text
cargo test stream_credit
```

Result: exit 1 with 36 expected compile errors. The failures named the missing `StreamCreditWindows`, `StreamCreditBinding`, `StreamCreditAllocation`, lifecycle error variants, `ChannelStreams::prepare_credited`, and `ChannelRegistry::credit_generations`. This was the expected missing-feature RED, not a fixture, syntax, or environment failure.

## GREEN implementation

- `StreamCreditWindows` uses one session identity, a channel map, a current `u64` bitmap, at most one draining `u64` bitmap, non-zero checked epochs, and one optional pending refill epoch. It allocates no per-credit objects.
- Exact 64-slot exhaustion, watermark 16, single pending refill, checked next-epoch activation, current/draining reordering, retirement, same-slot serialization, non-wrapping exhaustion, and channel/session removal are fail closed.
- Credit bindings pin exact V1 profile, session, route, RouteGrant digest, channel, channel generation, and revocation generation. Legacy/unselected channels retain the existing STREAM_OPEN path and cannot consume credits.
- `ControlSession::authorize_credited_stream` performs session-active, bound-channel, exact RouteGrant expiry, profile, generation, epoch/slot, stream capacity, P1F replay capacity, and audit checks before mutation. It then commits the credit and the infallible ordinary stream/P1F entry while holding one mutable session authority.
- Failed profile, expiry, slot, duplicate stream, capacity, replay-capacity, or audit preflight cannot mutate the credit bitmap or `used_stream_ids`; committed state is never restored.
- Revoke, close, successful forced drain, session close, and failed resume rollback discard applicable credit/profile state. Replay history remains session-wide and is not erased by channel cleanup.

## Focused GREEN evidence

All commands used the same `CARGO_TARGET_DIR` above.

```text
cargo test stream_credit::lifecycle_tests
cargo test credited
cargo test channel_registry::tests
cargo test credited_admission_commits_slot_and_replay_together_under_live_authority
```

Observed results:

- lifecycle: 7 passed, 0 failed;
- credited ChannelStreams: 2 passed, 0 failed;
- registry: 6 passed, 0 failed;
- live session authority/atomicity: 1 passed, 0 failed.

The focused tests cover exact slot/refill/epoch bounds, old/new reordering, same-slot race, profile/session/route/grant/channel/generation/revocation isolation, duplicate stream and slot behavior, P1F rejection without credit consumption, legacy downgrade rejection, exact grant/session expiry, sibling capacity isolation, thousands of never-consumed channels, 10,000 repeated invalid/duplicate/refill-flood attempts, and a fixed `CreditWindowState` size assertion.

## Final verification

Fresh final commands from `crates/nbsr-transport`:

```text
cargo test
cargo fmt --check
cargo clippy --all-targets -- -D warnings
git diff --check
```

Result: exit 0. Full suite: 163 passed, 0 failed, 1 ignored. The ignored test is the pre-existing P1F ten-minute evidence-only soak. Formatting, strict all-target Clippy, and diff whitespace checks passed without warnings/errors.

## Independent review and self-review

The read-only review initially found implicit V1 activation on legacy channels and missing live RouteGrant expiry enforcement. Both were fixed with explicit pending-channel profile selection, legacy default/no credit window, an exact registry-owned grant-live check, and live regressions. A second review pass found an expiry-boundary mismatch and resume-rollback profile leak; both were fixed (`now == expires_at` remains valid, `expires_at + 1` rejects; rollback clears profile/window state even on audit error).

Self-review confirmed:

- no `ControlEnvelope.request_id` or `monotonic_sequence` is used by credited admission;
- `used_stream_ids` and `ReplayHistoryLimit` remain the replay oracle/cap;
- no credit bit is set before stream/capacity/audit prepare succeeds;
- no legacy authorization branch was removed or weakened;
- no per-credit heap allocation, global queue, origin data, bearer credential, or speculative payload state was introduced;
- cleanup is channel/session scoped and does not erase replay history or sibling state.

## Concerns and non-claims

- The actual full-audit-queue failure and exact P1F cap are exercised by existing repository tests and the credited lower-level prepare tests; the new live credited-session test exercises the duplicate-replay atomicity path but does not independently refill the audit queue or construct a low-cap live session.
- Sender allocation/refill control transport and epoch retirement wiring are deliberately not connected to QUIC/control I/O in Task 2; the bounded APIs are pinned for the later runtime task.
- This task does not claim live credited-preface QUIC interop, ACCEPT/REJECT stream I/O, performance improvement, production readiness, or completion of later P2D tasks.

## Commit and publication

Task 2 files are committed locally only. No push, pull, merge, rebase, or protected-ref mutation was performed. The commit SHA is recorded after creation in the handoff response.
