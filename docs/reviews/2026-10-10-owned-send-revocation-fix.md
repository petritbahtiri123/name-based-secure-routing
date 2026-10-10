# Owned-send revocation / drive-drop correction

Local, uncommitted checkpoint on `codex/nbsr-v3-wp0-wp1`, base
`f6400959e93f32f3eec32372c60773c115344583`. No authority activation, commit,
push, deployment, dependency download or persistent machine-setting change.

## Defect and bounded correction

When revocation called `force_reset` while a pending owned `drive()` held the
stream mutex, retained payload and quota were released but the transport reset
could not acquire that mutex. Dropping only the future then left the operation
alive without RESET/STOP until another drive or owner destruction.

`owned_send.rs` now declares the existing unarmed `BorrowedSendCancellation`
guard before the stream mutex guard. On future Drop, the mutex unlocks first;
the cleanup guard retries reset only if cancellation/revocation is marked.
Ordinary drive cancellation remains a pause with retained offset/payload/quota.
No background task, new protocol decision, timeout, frame or quota limit changes.
The inherited receive/ACK future-drop limitation is not changed by this patch.

New tests in `owned_send.rs` establish zero and partial accepted payload progress
using authenticated loopback and a 64-byte transport window. They prove the
pending future owns the mutex, revoke, drop only that future without repolling,
and keep operation/stream/connections alive while observing peer RESET and STOP
with the existing code 1. They check payload/reservation clearing, zero quota,
released state ownership after owner Drop, rejected later drive, idempotent
terminal cleanup and successful sibling traffic. This tests terminal effects,
not the number of internal reset calls or wire retransmissions.

The only change to `control_read_tests.rs` is making its existing connection
fixture `pub(super)` for the sibling test module. Removing that visibility word
reproduces its exact pre-task SHA-256; the separate partial-frame-body test is
preserved. `quinn_adapter.rs` and both overnight report files are unchanged from
the start of this correction. New public documentation was added only after
the regression and library checks passed.

## Retained attempts and results

| Attempt | Result | Test / supervised duration |
| --- | --- | --- |
| Initial compile | Missing test-only `Duration` import; corrected, not behavioral RED | No tests executed |
| First behavioral run | 2 failed: partial-progress expected reset timeout; zero-progress fixture hit connection timeout because early sibling data consumed shared credit | 5.03 / 11.45 s |
| Corrected RED fixture | 2 failed at the intended peer-reset timeout after all phase, payload and quota assertions passed | 2.17 / 6.64 s |
| Minimal guard GREEN | 2 passed | 0.15 / 5.83 s |
| Library aggregate | 108 passed, 0 failed, 1 existing ignored soak | 6.23 / 10.45 s |
| Application-stream integration | 4 passed | 0.47 s |
| Stream-credit integration | 12 passed | 1.19 s; combined integration supervisor 24.89 s |
| Documentation tests | 16 passed (existing compile-fail examples) | 1.07 / 3.02 s |
| All-target benchmark Clippy, warnings denied | Passed | 7.83 s supervised |
| Default-feature library check | Passed | 1.41 s supervised |
| Cargo formatting and diff whitespace | Passed | Not separately timed |

The library suite includes normal repeated pause/resume, completed FIN/ACK,
completion idempotence, and completion/revocation quota-transfer regressions.
Its run preceded only the three public documentation lines; runtime and test
behavior did not change afterward. No full repository, hosted matrix, Linux,
WAN, capacity or large-connection trial was run. The existing ignored test is
`adversarial_soak_holds_replay_history_at_ten_thousand`.

The first PowerShell wrapper printed an empty exit field despite compiler
errors. Its logs remain retained; it is not counted as successful. Subsequent
runs used the Python supervisor with explicit Cargo exit codes. It enforces
95-second cutoff, at least 8 GiB starting disk, 6 GiB disk floor, a stricter
256 MiB per-run growth cap, 2 GiB RAM reserve and two build/test workers. All
subsequent children were reaped, with no resource/time abort. Each bounded run
used the existing verified Windows target cache and locked offline dependencies.

Raw logs and command/result JSON are under task-temp
`nbsr-owned-revoke-evidence`; the initial compile logs are
`control-read-owned-revoke-drop-red.{stdout,stderr}.log`. Adjacent JSON records
their hashes, final source/binary hashes and command results. The final patch
includes pre-existing dirty transport changes and is bound to the exact base;
it must not be represented as only this fix. The initial RED test-source bytes
were not separately snapshotted before formatting; retained logs identify the
assertions and attempts, while final-source hashes identify the verified fix.

Independent read-only review found no blocking correctness/security issue.
It confirmed guard drop ordering, ordinary pause preservation, faithful retained
owner tests and the restricted test-fixture visibility. It noted that unrelated
fixture setup failures can still hit early unwraps, consistent with existing
fixtures; expected regression failures explicitly clean up before assertion.
The reviewer did not execute tests or independently inspect RED/GREEN logs.

## Next small tests, before broader network trials

1. Reproduce inherited `receive_payload` and ACK-wait revoke-then-drop without
   repoll, retaining stream and connection. Separate quota release from prompt
   RESET/STOP; do not relabel the pre-existing limitation as this regression.
2. Characterize remote connection close while an owned operation is paused,
   before another drive or owner Drop. Current coverage resumes after close;
   it does not establish eager cleanup of a retained paused owner. Determine
   the intended ownership guarantee before calling retained state a bug.
3. Exercise repeated session/channel revocation combined with owner Drop and a
   live unrelated channel. This patch covers direct stream reset repetition and
   sibling traffic, not every session-wide ordering. Add only missing cases;
   normal completion idempotence and same-stream cleanup already have coverage.

CI's current-source authority failure remains explicit. The inactive two-file
candidate describes committed `f6400959`, not this new `owned_send.rs` change or
the pre-existing dirty body test. Any later authority decision must identify its
actual selected source/dependency scope. No hashes or validators were refreshed.
Root AGENTS guidance remains applicable without modification.
