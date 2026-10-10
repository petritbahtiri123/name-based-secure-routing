# Overnight robustness work: October 9-10, 2026

Latest checkpoint: October 10 10:57 UTC; body-pending coverage follow-up is local and uncommitted. Baseline: `e245bc357379b44449bb22f53a1c6a1c723fc1cc`.
Morning report target: October 10 09:00 Europe/Skopje (07:00 UTC); work cutoff
06:30 UTC. This checkpoint is an early completed iteration, not work left running.
All changes are local. No commit, push, bypass, downloads or system changes.

## Iteration 1: composite cancellation contract

Read the design, implementation and all six non-test `send_and_receive` call sites
in `perf_rust_source.rs`, plus representative integration/demo callers. They perform
one exchange per stream. The design explicitly disallows whole-composite restart,
but the method lacked API-local cancellation documentation.

A bounded characterization uses one authenticated loopback pair and three streams.
It observes request FIN and exactly six retained response-prefix bytes before
cancellation, avoiding timing guesses. The seven-byte request and six-byte prefix
retain 13 quota bytes. Restarting the whole method reaches the finished send
direction, returns ApplicationStreamFailed, resets the stream, clears the prefix,
and returns quota to zero. No duplicate request bytes arrive. Continuing only
receive_payload returns the exact 13-byte response, holding 20 bytes with the request
until explicit release. A fresh normal sibling also completes and releases quota.

This establishes no protocol defect, duplicate request, or quota leak. The smallest
justified improvement is rustdoc explaining the one-shot API, send-versus-receive
cancellation, unsupported restart, explicit send/receive phase management, the
original absolute deadline, and quota ownership. Runtime behavior is unchanged.
Callers cannot infer the active phase merely from a composite timeout; split the
operations when phase-aware continuation is needed. No new API was introduced.

## Actual validation

| Run | Passed | Failed | Ignored | Duration |
| --- | ---: | ---: | ---: | ---: |
| composite-response-characterization (carried into this iteration) | 1 | 0 | 0 | 0.16 s |
| overnight-composite-library | 101 | 0 | 1 | 6.05 s |
| overnight-composite-doc | 16 | 0 | 0 | 1.03 s |

Commands used the existing cached Cargo target, locked/offline dependencies,
benchmark-harness feature, two jobs and the existing bounded resource supervisor.
The one ignored test is the pre-existing ten-minute soak. Doc-tests are the crate's
existing 16 compile-fail examples; they do not by themselves prove prose accuracy.
Final formatting and whitespace checks passed. No integration suite, demo workload,
or benchmark was repeated for this documentation-only runtime change.

Independent read-only review found the characterization sound and requested a
precision correction: a retry resets only if it reaches the finished send direction;
size/channel-quota preflight rejection can leave response state intact. The final
rustdoc includes that qualification. An initial text replacement missed CRLF;
a checked normalized edit applied it, and the reviewer confirmed the final text.
The final prose correction followed tests but changed no executable code or examples.
No remaining review blocker or failed test is known for this iteration.

## Scope, resources and cleanup

Exact changed files relative to baseline:

- crates/nbsr-transport/src/quinn_adapter.rs (rustdoc only)
- crates/nbsr-transport/src/control_read_tests.rs (one characterization)
- docs/benchmarks/OVERNIGHT_ROBUSTNESS_2026-10-10.md (this report)
- docs/benchmarks/OVERNIGHT_ROBUSTNESS_2026-10-10.json (evidence manifest)

Existing unrelated untracked files remain untouched. Local log basenames are
`control-read-composite-response-characterization`, `control-read-overnight-composite-library`
and `control-read-overnight-composite-doc`, each with stdout/stderr suffixes; raw logs
remain outside the repository. The JSON manifest records source and report hashes.

Disk headroom was 14.88 GiB at the start and 14.84 GiB at the checkpoint. Final free
RAM was 6.87 GiB, above the 2 GiB stop reserve. A sandboxed CIM read was unavailable;
a permitted read obtained actual RAM, and no zero-RAM interpretation was used.
All invoked test processes exited successfully. The final process inventory found
zero instances of the owned library test executable. No containers were created;
no container or unrelated-process cleanup was performed. No background load remains.

## Iteration 1 next decisions

No further justified production fix was established in this composite investigation.
Retain the characterization and documentation for review. Material phase-resumable
composite/echo APIs remain deferred for explicit design input. Benchmark framing is
not a demonstrated production issue and was not expanded into speculative work.
Return this completed checkpoint to the parent for the morning report; do not keep
processes running or invent changes merely to fill the overnight window.


## Iteration 2: benchmark-frame revocation wakeup

Read the P2A established-data-plane design and actual send/read loops before changing
anything. Benchmark frame cancellation/restart is not a resumable API: callers finish
or invalidate the repeat, with no replacement stream. Ordinary partial-frame retry
was therefore not labeled a new defect. No new framing protocol, quota policy, or
phase-resume API was introduced.

A concrete separate gap was reproduced: benchmark frame methods held the async
stream mutex while awaiting I/O, but did not observe the shared revocation Notify.
force_reset marked the stream cancelled but could not acquire that mutex. Both a
pending frame read and a backpressured frame write remained pending until the
250 ms test deadline despite revocation. The write case proved the 4096-byte length
prefix had reached the peer. The existing initial-state checks also did not return
consistent ApplicationStreamRejected after revocation.

The first diagnostic used the ordinary two-byte-prefix fixture; the reproduced
suite then used only 64-byte loopback windows. Each final test owns one connection
pair at a time, with bounded payloads and cleanup. Normal empty and nonempty frames
continue on the same stream without FIN. No benchmark workload was run.

The minimal fix is confined to benchmark-harness methods: register Notify before
waiting for the mutex, check cancellation before I/O, select revocation across the
whole frame length/body future, and check cancellation again before returning a
result. A named, unarmed existing cleanup guard is declared before the stream lock;
if the stream has been revoked, it finishes reset after unlocking, including when
the pending future is dropped without repolling. It does not reset healthy streams
on ordinary caller cancellation. Such cancellation remains unsupported for resume:
abandon the stream and invalidate the repeat. No changes to normal FIN behavior,
framing bounds, default-build runtime behavior, or benchmark quota accounting.

Four regressions now cover blocked read, blocked write, normal persistent framing
plus revoked reuse, and revocation followed by future Drop in both directions.
The latter verifies peer-visible reset while keeping the stream owner alive, later
read/write rejection, and zero payload reservations. A small test-fixture factory
adds optional window configuration while leaving all existing callers unchanged.

| Actual run | Passed | Failed | Ignored | Duration |
| --- | ---: | ---: | ---: | ---: |
| overnight-frame-revoke-red (initial diagnostic) | 0 | 1 | 0 | 0.41 s |
| overnight-frame-tiny-red | 0 | 3 | 0 | 0.57 s |
| overnight-frame-green | 3 | 0 | 0 | 0.29 s |
| overnight-frame-library (includes fourth regression) | 105 | 0 | 1 | 6.28 s |
| overnight-frame-codec | 6 | 0 | 0 | 0.03 s |

The codec run filters to six frame tests and excludes runtime-scaling tests.
Default-feature library cargo check passed (5.10 s); all-target Clippy with warnings
denied passed (8.60 s). Formatting and diff whitespace checks passed. All commands
used locked/offline cached dependencies, at most two jobs and unchanged resource
limits. The only ignored library test remains the existing ten-minute soak.

Independent review found no blocker: notification covers length and body I/O,
pre/post checks prevent revoked success, reset runs after unlocking, and ordinary
cancellation/FIN/quota behavior remains unchanged. Optional finer coverage of a
provably body-pending read was noted; the deterministic blocked-read regression
uses an incomplete length, and the encompassing select covers the body by code
inspection. No test or assertion was weakened to obtain a pass.

Final resources at 22:35 UTC: 14.83 GiB disk free and 6.79 GiB RAM free. Final process
inventory found zero instances of either owned library or P2A codec test executables.
All runner processes completed; no containers were created and no background work
remains. There were no resource-cutoff aborts or dependency downloads.

The exact changed-file set remains the same four files listed above: two Rust files
plus this report and its JSON manifest. The composite documentation/characterization
from iteration 1 is preserved. Baseline e245bc35 is unchanged; no staging, commit,
push, rule changes, or unrelated cleanup occurred. Known red attempts are preserved
in local logs and the manifest; no unresolved regression failure remains.

Next step: review the combined small local diff. Keep material composite/echo resume
APIs and ordinary benchmark-frame restart out of scope. This iteration establishes
revocation robustness only, not performance, capacity, or new delivery guarantees.

## Iteration 3: untracked stream-admission boundary

The baseline and branch were verified unchanged. The `.agents` directory is empty;
no nested AGENTS.md or SKILL.md was found under crates or docs. The B3 admission
record concerns connection acceptance, distinct from this stream-level inspection.
Reviewed credited open/accept, terminal admission cleanup, tracking/reset, and
session credit allocation/authority checks, then the existing integration tests.

Existing coverage already tests dropping a timed-out source admission, retaining
consumed credit/replay history, admitting a distinct sibling, exhaustion/refill,
and rejecting revocation before destination commit. These were not duplicated.
A new one-stream deterministic characterization polls an accept before a peer
stream exists, commits destination revocation, and polls again. It remains pending:
there is no tracked ApplicationStream to receive a revocation notification yet.
Peer progress then resolves both ends as ApplicationStreamRejected. The source
permit is unavailable after terminal cleanup; destination authority also rejects
its permit. This checks permit availability, not a direct count of quota entries.

This is a confirmed delayed-revocation boundary, not a demonstrated stale admission
or payload quota leak. Code inspection finds the same pre-tracking interval while
source open_bi waits for transport credit and while destination reads a preface.
Those two cases were NOT dynamically reproduced in this iteration. Source credit
allocation and destination authorization recheck authority after their waits.
No application payload reservation occurs in these pre-admission waits.

The smallest change is API rustdoc requiring a caller-owned whole-operation
deadline and describing cancellation ownership and retained replay history. No
runtime behavior or permanent control-stream claim changed. Automatic revocation
wakeup before a stream exists needs a broader channel/session cancellation design;
that material API/ownership decision is deferred, not represented as fixed. This
characterization must be updated if such a design is approved later.

Validation used the existing offline cache with two jobs and the copied existing
95-second resource supervisor. The exact regression passed 1/1 in 0.18 seconds
(build 3.73 seconds), followed by all 12 stream_credit_integration tests passing
in 1.59 seconds (build 25.49 seconds), zero failed/ignored. Formatting and diff
whitespace checks passed. No library suite, Clippy, benchmark or large workload
was repeated for this documentation/characterization-only iteration. `rg` was not
installed; PowerShell source reads were used. No build/test attempt failed.

Logs and runner are retained in the private local evidence directory, with basenames
control-read-overnight-untracked-accept and control-read-overnight-admission-suite.
The manifest records commands, source/binary/log hashes and an exact dirty patch.
Final observed headroom: 14.81 GiB disk, 6.04 GiB RAM; zero matching owned test
processes. Both supervised invocations exited 0. No containers were created.

This iteration additionally changes tests/stream_credit_integration.rs; earlier
changes in both Rust source files remain intact. No staging, commit, push,
download, system setting change, or unrelated cleanup occurred. Root guidance
remains applicable unchanged. Independent read-only scoped review found no correctness/security blocker. It confirmed the caller-deadline wording and deferred architectural decision, and identified the same explicit dynamic-coverage and permit-versus-counter limits recorded above.


## Iteration 4: owned-send and partial-receive teardown review

Bounded static review found no new concrete retained-quota leak, stale operation,
or unintended reuse requiring a reproduction or patch. Read the approved owned-send
contract and WP4 accounting/lifecycle decision before examining owned_send.rs,
SharedApplicationStream, PayloadReceiveState, ChannelByteReservation, tracking,
reset, close and Drop paths, plus existing ownership tests. No code/test file changed.

Ownership findings:

- OwnedSendOperation holds the strong state reference and an exclusive stream
  borrow. The stream registers only a Weak state reference; tracking registers
  only Weak stream/quota references. No strong-reference cycle was found.
- Unfinished operation Drop calls force_reset, clearing owned payload/reservation,
  retained receive state and completed reservations. Completed operation Drop
  preserves FIN and leaves completed quota with the stream, as designed.
- A terminal write error observed by drive aborts before returning. Repeated drive
  cannot revive an aborted operation. Revocation and enforced-drain resets reach paused state
  through the weak registration without requiring its drive future to be repolled.
- Partial-receive reservations belong to the stream state; cancelling a receive
  future retains them intentionally. Terminal read error discards that state and
  sets failed. Further payload reads and begin_owned_send reject failed state.
  Final shared-stream Drop drops the reservation vectors and releases quota.
- Receiving a QUIC reset does not by itself establish a whole-stream cancellation
  policy for the opposite send direction. The documented terminal-read guarantee
  concerns further payload reads. No blanket reset/half-close policy was invented.

Existing coverage inspected, not rerun: payload_reset_discards_partial_state_and_fails_closed;
payload_stream_drop_releases_unfinished_reservations;
payload_revocation_releases_idle_and_pending_cancelled_receive;
owned_send_abort_drop_and_revocation_release_partial_send;
owned_send_peer_close_releases_paused_ownership;
owned_send_completion_racing_revocation_cannot_resurrect_quota;
owned_send_completed_fin_ack_and_terminal_quota_ownership; and owned-send bounds,
operation-mismatch and prior-write tests. These cover the concrete branches sought,
so no duplicate abort/revocation test was added.

Important evidence limit: the peer-close test resumes drive before checking quota.
A peer close/reset while the owner remains deliberately paused is not an eager
application-state cleanup notification. AuthenticatedConnection::close closes Quinn
but does not itself sweep retained application ownership. The approved contract
creates no background watcher: the owner must resume to observe terminal I/O, or
abort/drop at its existing absolute deadline. Retained accounted state with a live
owner is not evidence of a leak. No new promise of autonomous cleanup is made.

Actual checks this iteration: code hashes match the iteration-3 checkpoint; static
ownership/contract review only. Zero test/build commands, zero new pass/fail counts,
zero workloads. Historical validation counts remain historical. At 22:49 UTC disk
free was 14.81 GiB; matching library and stream-credit test process inventories were
both zero. No processes/containers were created. RAM was not remeasured because no
build/trial ran; the last measured value remains iteration 3's 6.04 GiB at 22:46 UTC.
Independent read-only scoped review found no new ownership blocker and confirmed the limits above, including that initiating drain alone is not enforced terminal cleanup. No guidance update is needed: workflow,
resource limits, setup and protocol semantics are unchanged.


## Final consolidated handoff

Fresh independent aggregate review compared the complete code diff against
`e245bc357379b44449bb22f53a1c6a1c723fc1cc` and reviewed this report/manifest. It found
no correctness/security blocker: full-frame notification coverage, pre/post cancel
checks and cleanup-after-unlock ordering interact correctly with existing guards;
ordinary frame cancellation remains unchanged. The reviewer confirmed deterministic
phase checkpoints and documentation limitations. Its minor report correction to
Europe/Skopje is applied; the requested report target remains October 10 09:00
local / 07:00 UTC. No further justified low-risk patch identified.

Final validation was split into bounded offline groups against final code contents:

| Check | Passed | Failed | Ignored | Test duration | Build/check duration |
| --- | ---: | ---: | ---: | ---: | ---: |
| Final library suite | 105 | 0 | 1 | 6.25 s | 6.01 s |
| Final documentation tests | 16 | 0 | 0 | 1.05 s | 0.27 s |
| Final all-target Clippy, warnings denied | n/a | 0 | n/a | n/a | 7.61 s |
| Stream-credit integration, exact unchanged final code (iteration 3) | 12 | 0 | 0 | 1.59 s | 25.49 s |
| Frame codec, unchanged runtime (iteration 2) | 6 | 0 | 0 | 0.03 s | 15.09 s |

The intentional ignored test remains
`channel_streams::tests::adversarial_soak_holds_replay_history_at_ten_thousand`, the
existing evidence-only ten-minute soak. Nothing newly ignored. The 16 doc-tests
are existing compile-fail examples; prose correctness is supported by review.
Formatting and diff whitespace checks passed. The earlier default-feature check
passed before later rustdoc/test-only changes; no new default runtime code changed.
Final Clippy newly covers the integration characterization. The final library run
consolidates the interacting guards on final source; the unchanged integration and
codec suites were not repeated. No broader benchmark/deployment gate is claimed.
Historical red attempts remain retained; there is no unresolved failed regression.

Exact final task-owned changed files (superseding historical per-iteration lists):

- crates/nbsr-transport/src/quinn_adapter.rs
- crates/nbsr-transport/src/control_read_tests.rs
- crates/nbsr-transport/tests/stream_credit_integration.rs
- docs/benchmarks/OVERNIGHT_ROBUSTNESS_2026-10-10.md
- docs/benchmarks/OVERNIGHT_ROBUSTNESS_2026-10-10.json

One runtime fix is limited to benchmark-harness frame revocation. Composite and
admission improvements are characterization/documentation; ownership review was a
negative finding. Material composite/echo resumability and pre-tracking admission
wakeup architecture remain deferred. Ordinary frame cancellation still abandons
the stream/repeat. No explicit body-pending read checkpoint, exhausted-open-credit
or partial-preface dynamic test was added; inspection-only limits remain. Retained
paused ownership requires its documented owner actions. No performance, capacity,
production-readiness or delivery guarantee follows from these local tests.

The manifest contains final source, binary and log hashes, exact cached/offline
commands and dirty patch identity. Raw final logs use control-read-overnight-final-
{library,doc,clippy} basenames under the private local evidence directory. Manifest
self-checksum is retained separately there to avoid a self-referential hash.
At 22:52:55 UTC free disk was 14.78 GiB and free RAM 6.07 GiB. Observed library,
stream-credit and codec test process counts were all zero; every final supervised
runner exited 0. No containers or background work remain from this task.

Safe handoff: all five task files remain uncommitted on codex/nbsr-v3-wp0-wp1;
HEAD is unchanged. Unrelated tracked/untracked work is preserved. No staging,
commit, push, downloads, setting changes or unrelated cleanup occurred. Root
guidance remains applicable without modification. Work is stopped rather than
held open until morning; the parent retains the scheduled report responsibility.


## October 10 local publication preparation

The user subsequently authorized committing these five scoped files locally.
Earlier no-commit statements describe the overnight checkpoints. Source hashes
still match the reviewed final code, and the aggregate review remains applicable.
No new implementation changes were introduced in this publication step.

Publication reruns used the same verified cache, locked/offline dependencies,
two jobs and bounded resource supervisor: library 105 passed / 0 failed / 1 existing
ignored soak (6.43 s; build 4.84 s), stream-credit integration 12 passed / 0 failed /
0 ignored (1.27 s; build 1.39 s), and all-target Clippy with warnings denied passed
(1.17 s). Formatting and whitespace checks passed. The unchanged final-content
16 doc-tests and six frame-codec tests were not repeated without a code change.

Publishability review found machine-specific absolute evidence paths; these have
been replaced by local artifact labels. The original private records and raw logs
are retained outside the repository. `local-evidence/` and `cached-target/` in the
manifest identify retained local artifacts, not committed directories or portable
paths. No raw logs, binaries, private keys, tokens or machine usernames are included
in this five-file publication. Historical failed attempts and limitations remain.
SHA-256 source hashes identify tested working-tree bytes; staged Git blob IDs also
identify commit content despite Windows newline normalization.

At 07:44:05 UTC, free disk was 14.40 GiB and RAM 6.44 GiB, with zero matching library
or integration test processes. All supervised checks exited 0; no containers were
created. No architecture or resource-policy changes were made.

Push is withheld. A read-only GitHub check found the remote branch still at the
baseline and protected by active ruleset `protect nbsr` (22457059), applying to all
refs. It restricts updates and requires signed commits, alongside deletion and
non-fast-forward restrictions. The legacy branch-protection endpoint returned 404;
the branch rules endpoint and ruleset detail confirmed current protection. Direct
update therefore requires a ruleset bypass actor; an unsigned local commit also
requires bypass of the signature rule. No push, rule change, force push or bypass
has been attempted. A fresh specific push approval remains necessary.

## Post-publication follow-up: body-pending frame revocation

Commit 8e548588c6ff636bb7a29a8202adb9a37e5110c1 was subsequently published to
codex/nbsr-v3-wp0-wp1 using the specifically approved update/signature bypass.
The exact remote SHA was verified; GitHub reported zero workflow runs, check runs
and commit statuses for that SHA. This is absent CI, not passing CI. The following
new work remains local, with no additional commit or push.

Added benchmark_frame_body_pending_revocation_resets_and_releases_ownership.
One authenticated loopback connection uses 64-byte windows and a single application
stream. The peer sends a complete length of eight plus one body byte, without FIN
or the remaining seven bytes. A cfg(test)-only atomic checkpoint is stored after
length validation and body allocation, immediately before read_exact of the body.
The same poll returning Pending with checkpoint eight proves body I/O is pending;
timeouts bound failures rather than establish the phase. This does not assert that
the first body byte was consumed. The checkpoint field is also benchmark-feature
gated, and is absent from non-test builds. No public API or runtime behavior changed.

After force_reset, the test observes ApplicationStreamRejected, released stream
mutex, strict peer ReadError::Reset before connection cleanup, and rejected reuse.
It checks zero payload quota and empty retained receive/completed reservation state.
After dropping the fixture, its Weak shared-stream reference cannot upgrade and
quota remains zero. Benchmark framing does not charge payload reservations; these
checks do not claim allocator-wide accounting of the temporary eight-byte buffer.

The FIRST run against existing revocation behavior passed: 1/0/0 in 0.15 s (build
10.83 s). This is added regression coverage, not a new runtime fix. The library
suite then passed 106/0/1 in 6.30 s (build 0.25 s), with only the same existing
10-minute soak ignored. Independent review caught a test failure-path issue: an
unexpected Ready at the checkpoint would be repolled before cleanup. The test now
skips that repoll and reaches cleanup before asserting failure. Reviewer confirmed
no remaining blocker. Final focused rerun passed 1/0/0 in 0.16 s (build 4.14 s).
All-target Clippy with warnings denied passed in 10.66 s; formatting and whitespace
checks passed. Broad library results precede only that diagnostic-path correction;
no broad suite was needlessly repeated. No tests failed and no assertions were
weakened. Integration, codec and doc suites were not repeated for test-only code.

This closes the earlier body-pending inspection-only limitation. Pre-tracking
admission wakeup and composite/echo resumability remain deferred; no new runtime
defect or architecture decision was established. Ordinary frame cancellation still
requires abandoning the stream/repeat.

Changed locally: quinn_adapter.rs (test-only checkpoint), control_read_tests.rs
(one regression), this report and its manifest. Raw logs are retained privately
under control-read-frame-body-{first,library,reviewed,clippy} names. At 10:56:50 UTC,
free disk was 14.30 GiB and RAM 6.12 GiB; zero matching library test processes,
all supervised exits 0, no containers created and no background work. Offline
cached dependencies, at most two jobs and unchanged 95-second guards were used.
No new commit/push, settings change, dependency download or unrelated-file change.
Root guidance remains applicable unchanged.
