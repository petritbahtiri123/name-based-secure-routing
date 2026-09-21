# Native Lifecycle Coordinator Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans inline, task by task.
> Existing autonomous authorization applies; no routine design/implementation
> approval loop. Keep protected protocol/security contracts unchanged.

**Goal:** Replace campaign-only manual two-endpoint barriers with a reproducible,
bounded native lifecycle control path and an external execution definition.

**Architecture:** A per-host controller delegates transport ownership to the
existing `linux_native_lifecycle.execute`. A separate control thread observes
local markers and accepts a small private stdin JSON command set; stdout reports
phase events. A two-host coordinator prepares the source first, transfers
destination readiness, requires both all-active observations, holds two seconds,
releases destination then source, observes ACK/report readiness, cools down two
seconds, and validates both retained peer packages. Existing authenticated SSH
management supplies remote execution; it is not NBSR protocol or federation.

**Tech Stack:** Python standard library and existing native release peers.

**Spec:** `docs/benchmarks/EXTERNAL_NATIVE_LIFECYCLE_PEER.md`, especially the
coordinator contract, cancellation limits and pair-gate claim boundaries.

## Constraints

- Preserve count, finite offered rate, two-shard semantics, materialized payload,
  all-active hold, release/ACK behavior and all eleven zero-ownership assertions.
- No transport/idle timeout increase, keepalive, production optimization, changed
  authority, new trust, relaxed TLS or public protocol change.
- Native local private fixtures/control/output; never transfer keys in public
  output. Reject stale marker sets and private/output path overlap.
- Existing per-host executable owns, kills and reaps its child. Keep its proven
  cancellation path; do not invent PID-based cleanup of unrelated processes.
- Bound private control input, reject unsupported/out-of-order commands, cancel
  on control EOF/error, and retain partial outcomes. Checksums are not attestation.
- Physical external machines remain EXTERNAL_HARDWARE_REQUIRED. Docker transport
  smoke does not prove SSH/server/WAN behavior or sustainable capacity.
- Current task weekly baseline is 7%; hard ceiling is 27% total account usage.
  Reserve reporting space and checkpoint unfinished stages before the ceiling.

## Task 1 — Per-host barrier/controller

- [x] Add literal RED tests for complete named sets, failed markers, early release,
  early cooldown release, wrong-role operations, malformed input and cancellation.
- [x] Implement `scripts/performance/linux_native_lifecycle_control.py`, with
  local barrier state independent of remote clocks and a bounded control stream.
- [x] Reuse the existing native CLI parser and `execute`; keep child cleanup in
  that implementation. Source preparation must precede destination listening.
- [x] Preserve local socket bindings and public marker copies. Report functional
  completion only after the delegated runner succeeds; no timing qualification.
- [x] Run focused tests, Ruff, one focused ownership/security review and commit.

## Task 2 — Two-host coordinator

- [x] RED tests for phase order, both-active hold, destination-first release,
  peer failure/cancellation, strict SSH command construction and safe collection.
- [x] Implement a coordinator using persistent control streams. SSH uses batch
  authentication and strict host-key checking; credentials/hosts are supplied
  by the operator. Do not discover or contact unrelated machines.
- [x] Bound evidence transfer and reject traversal/symlinks/special files. Collect
  both peer outputs before independent pair validation. Preserve every failure.
- [x] Validate three native namespace smoke pairs and explicit cancellation/error
  cases with exact release/source provenance; state unexecuted SSH/hardware gaps.
- [x] Update the external runbook, preserve checksums, verify and commit.

## Review focus

1. Missing/partial input, EOF or a second cancellation must not orphan owned work.
2. Stale markers, private path overlap and symlinks must fail closed before writes.
3. Incomplete active/ACK sets or early release must not produce passing evidence.
4. Independent hosts have independent monotonic clocks; use per-host elapsed
   checks and coordinator elapsed hold, never subtract foreign timestamps.
5. Process cleanup, functional pair acceptance, sustainable admission and real
   external validation remain distinct claims.

If a stage cannot be completed within the remaining budget, retain a clean
atomic checkpoint and name the unfinished acceptance checks precisely.

## Execution ledger

Task 1: 22 barrier/input RED failures, then GREEN; five endpoint/parser RED failures,
six delegation RED failures, and two identity RED failures were also observed.
The current focused suite is 68 PASS with Ruff and diff checks passing. Source
PID/sample mismatch and duplicate socket inodes now reject before acceptance.
The per-host endpoint delegates child ownership to the existing native runner;
its control observer uses one local directory inventory per poll. Live release
smoke and EOF cancellation evidence are the next gate, not yet claimed here.

Task 2 implementation checkpoint: 106 focused tests pass, including real owned
local relay deadline/EOF tests. Strict SSH command construction, bounded archive
transfer/extraction, per-host phase clocks, and independent endpoint/pair gates
are implemented. One focused independent review found that failed startup could
collect an unowned preexisting output directory. A literal RED regression now
proves no collection occurs before a ledger-validated live prepared/ready event;
the correction and scoped re-review passed. Failed pre-phase output stays remote,
with local management/stderr retained and ownership explicitly unconfirmed.
Release Docker smoke, live remote EOF cleanup, and real SSH validation are not
yet claimed. No production Rust/Go or frozen contract changed.

Live gate at 3dfd9f8a: three 16-bundle positive pairs, five 512-bundle positive
pairs, three source EOF and three destination EOF cases pass. The first
25db6831 integration failure (Python buffered-stdin daemon shutdown abort 134)
is retained; the stop-aware descriptor reader correction has literal RED/GREEN
and 107 passing focused tests. All fourteen new live cells pass their declared
functional or negative-cancellation gates. Independent analysis verifies the
coordinator and local hold/cooldown clocks, markers, socket bindings, peer
provenance, successful ownership cleanup and separately observed process absence.
See `evidence/performance/v2/native-lifecycle-coordinator-3dfd9f8a/summary.md`.
Actual two-host SSH/physical-hardware validation remains explicitly unexecuted.
