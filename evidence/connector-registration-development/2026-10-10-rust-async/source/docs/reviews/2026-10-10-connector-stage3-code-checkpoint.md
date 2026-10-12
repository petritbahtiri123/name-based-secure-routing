# Consolidated Stage 3 code-only checkpoint

Base `c7abbc4423a9ad05cea9cdf6678c231a34cafd59`, branch `codex/nbsr-v3-wp0-wp1`. The approved development-only
slice now includes strict Go/Rust codecs, Rust registration ownership, Go attempts/
renewal, and both asynchronous cleanup fixture compositions. **Real Stage 3 remains
partial; stages 1-2 remain 2/10 complete.** No live activation or publication.

## Latest Rust composition

`connector_cleanup.rs` is test-only. `begin_cleanup` makes the exact connection
terminal, clears its pending exchange, withdraws eligibility and retains a private
cleanup ticket. Its snapshot uses the existing full session and Owner fields,
including registration generation; no new wire handle or lifetime policy is added.
A synthetic backend completes a cloned ticket. First result wins and notification
wakes waiters; callbacks never mutate the gateway. Dropping a future without repoll
or selecting a controlled deadline leaves ticket, owner and quota retained.

`finish_cleanup` validates the currently retained attempt, full session and owner
before applying confirmed success. Failure permits an explicit new retry ticket;
stale/duplicate callbacks cannot release a successor, even after connection-ID
reuse. Synchronous close, expiry polling and termination cannot bypass a retained
ticket. Repeated begin calls return the same ticket, not a backend dispatch.
The caller remains responsible for the synthetic backend; no worker, timer, socket,
busy loop, real backend timeout or application-work grace is introduced.

This reuses the previously inspected Core terminal-before-cleanup/exact-ownership
rules and approved connector lifetime separation. It does not change frozen Core
cleanup implementations or reinterpret deny-new as termination of active work.

## Exact validation and limits

| Component/check | Most recent result | Freshness/scope |
|---|---|---|
| Rust codec + registration/cleanup | **1 + 18 passed**, zero failed/ignored | Fresh latest run; five new async tests |
| Rust Clippy `-D warnings` and rustfmt | PASS | Fresh; only the two development test targets/new modules |
| Go connector + CBOR | **19 + 3 top-level tests; 67 + 10 pass events**, zero failed/skipped | Retained preceding Go checkpoint; all six Go sources unchanged |
| Python config/CRP/model/federation/CBOR | **462 passed**, zero failed/skipped | Retained earlier checkpoint; affected Python sources unchanged |
| Development generator | **27 artifacts exact** | Retained check; registry/vectors unchanged |
| Go vet/gofmt and Python Ruff | PASS | Retained checks for unchanged implementations |
| Source preservation and diff/index | PASS | Fresh: 37 prior source/vector files unchanged; frozen tracked registry/build/transport files unchanged; index empty |

Go event counts include parent tests and subtests; they are not added to the
Python/Rust counts as unique scenarios. The new Rust tests cover drop without
repoll and retained quota, delayed/duplicate completion, caller deadline, failed
close/retry/stale generation, and unowned/wrong-gateway isolation. Independent
inspection found no blocking ownership, lost-wake or cancellation defect.

The latest initial red was a missing-module/API compile failure, not a reproduced
live backend defect. All six latest runs are retained. Earlier 31 development and
7 Go cleanup runs, including cache permission/compile failures, behavioral red
tests and corrected Clippy diagnostics, remain in their original manifests; no
historical evidence is refreshed. Latest final checks have no failure or skip.

**Not run/proven:** a real backend, live sockets, live Go/Rust registration exchange,
authenticated registration-action/revocation producers, actual TLS-exporter
composition, real asynchronous backend completion bounds, durable identity,
readiness, application relay, full repository suites, race detector, WAN/capacity
or deployment validation. Python/Go were not needlessly rerun for this Rust-only
change. Synthetic notification success is not evidence of real backend shutdown.

## Scoped uncommitted inventory

The JSON manifest lists every path and exact hash. The 41 development package
files comprise:

- Rust: `connector_control.rs`, `connector_registration.rs`, `connector_cleanup.rs`
  and their two integration-test files (5).
- Go: codec, coordinator, cleanup adapter, their three tests and package README (7).
- Python: development-vector generator and its package regression (2).
- Separate development registry, 25 CBOR vectors and their manifest (27).

Six shared tracked guidance/status/profile/plan/overnight files carry current scope
and evidence links. They already contained earlier local work; their entire diffs
must not be treated as exclusively this slice. Dated reports/manifests and evidence
directories are additional deliverables. Current-turn implementation changes are
only the new Rust cleanup module and the existing development owner/test files.
Prior paused-peer tests, connector models, Stage 2 config, outreach files and
unrelated evidence remain preserved and outside this scoped implementation inventory.
Nothing has been staged, committed or pushed.

## Resources and cleanup

Latest six runs used the existing offline cache, at most two build jobs, 95-second
work/120-second cleanup ceiling, 8 GiB starting disk, 6 GiB floor, stricter 256 MiB
growth guard and 2 GiB RAM reserve. All direct children were reaped, no resource
abort; final read-only process inventory found zero relevant processes. No task
containers, workers, downloads, credential/trust/network/security changes or
unrelated deletion. Exact commands, durations, source/binary hashes and failures
are in the companion manifest and retained evidence directory.

## Remaining gates and smallest next security authorization boundary

Both language cleanup fixture compositions are implemented. Remaining real Stage 3
gates are the actual provider bindings: authenticated transport/peer identity,
registration-specific authority and revocation provenance, actual exporter binding,
backend-owned cleanup/timers and their bounded completion/cancellation evidence,
and independent live Go/Rust exchange before any READY claim. No active-work or
Stage 4 expansion follows from these results.

The smallest next security decision is to review the exact development-interface
to real transport/authority-provider mapping before implementing or activating it;
synthetic receipts must never become an accept-all runtime provider. Live activation
requires explicit authorization. A new backend cleanup deadline, forced-release
rule or active-work grace would also require a concrete policy decision first.
No such decision was needed or silently selected for this code-only composition.
