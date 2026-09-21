# Prepared-source startup and retained native 512 limits

Measurement source: `a1ac83c8431836d5cd2b4a9bd04a7947a2a71a3b`.
Release binaries are byte-identical to the preceding a401567d build. The only
implementation change is the optional Python source preparation barrier.
No production Rust, protocol, cryptography, transport deadline or idle lifetime
changed. This is functional shared-WSL namespace evidence, not capacity timing.

## Proven harness startup defect

Read-only reanalysis of all five original a401567d 512 cells finds source/destination
first-resource-sample gaps of 4.551, 5.434, 20.053, 4.963 and 4.540 seconds.
Destination logs contain respectively 0, 1, 4, 0 and 0 handshake timeouts. The
failed source IDs are respectively none, 511, 508–511, none and none.
The benchmark starts serial finite `accept_one` calls when destination readiness
is published. Each empty five-second wait consumes one of the declared slots;
source hashing, environment checks and executable copying previously happened
after this clock started. These sampled gaps alone are correlation, not exact
timestamps of timeout events.

A controlled counterfactual then used three counterbalanced 16-bundle pairs,
identical release binaries, 100 offered/s, two source shards, one guest CPU per
role, and a deliberate six-second management delay. With the old startup order,
all three cells lose one destination slot and fail with 15 active bundles and
client 15 timing out. Preparing the source before starting the destination passes
all three cells: 48 completed connections, both-endpoint release, source ACKs,
and all eleven final ownership counters zero. The independent pair gate accepts
the three successes and rejects the three failures. No failed result is replaced.

`--prepare-before-readiness` finishes preflight/copy before publishing
`source-prepared.json`, then awaits fresh validated readiness for at most 30
seconds without creating a transport. It is cancellable. The existing child
controller and transport budgets are unchanged. Literal RED captured two failing
ordering tests; the focused lifecycle/pair suite then passes 33 tests, with Ruff
and diff checks passing.

## 512 remains PARTIAL

The first prepared 512 progression passes its first cell. Its second reaches all
512 active bundles at both endpoints but fails during release/close. Binding
observations start 5.327 and 7.712 seconds after paired-active publication, while
the actual snapshots take only 0.056 and 0.002 seconds. Existing close diagnostics
record releases after the ten-second idle lifetime. Cancellation then exceeds the
controller's existing 15-second wait; owned containers are stopped. The incomplete
cell and infrastructure failure are retained; the remaining three planned cells
were not run. No successful cleanup is asserted for this interrupted cell.

The next explicitly separate cohort runs the same socket identity observation
inside each existing watcher at all-active, before publishing the active marker.
This removes sequential Docker exec/interpreter launches from the held interval.
Both-endpoint all-active gating, the two-second hold, resource cardinality,
100/s, two shards, release/ACK semantics and two-second cooldown remain unchanged.

All five original attempts are retained: repeats 1, 2 and 4 pass 512/512 with zero
final ownership; repeats 3 and 5 fail during handshake. At cancellation their
source/destination active-marker prefixes are 7/6 and 203/201; these are partial
prefixes, not complete final admission accounting. Source starts only about
0.144 and 0.114 seconds after destination sampling, so these failures cannot be
attributed to the proven pre-launch five-second empty-wait defect. Failure-only
live socket snapshots report zero cumulative source drops in both cells. The
destination reports zero drops in repeat 3 and 68 in repeat 5. The snapshots do
not timestamp those drops or prove that they caused the handshake stalls; closed
sockets and earlier transient state are not observed. The remaining
handshake-progress cause is **UNRESOLVED**. No buffer change follows this mixed
evidence without causal attribution.

The independent pair gate accepts all three scale successes and rejects both
failures. Thus 512 remains **PARTIAL_FUNCTIONAL_NAMESPACE_SCALE**, and 256 remains
the largest five-repeat fully successful native held cohort. Historical 2048
loopback evidence has a different fixture and is neither superseded nor promoted.
No additional 512 reruns seeking favorable outcomes follow this cohort.

For the three complete final 512 cells, median whole-process peak RSS is
204,865,536 source bytes and 175,767,552 destination bytes. Peak FD medians are
524/9 and thread medians 4/2. These are coupled resource/process measurements,
not bytes per connection/session/channel/stream or same-process retention proof.

## Preservation and limits

One initial setup attempt timed out importing the Git bundle before any workload
started. It is retained separately. A previously prepared campaign-owned checkout
was cached to avoid repeating that import; source SHA and release hashes were
still checked. No timeout was enlarged to make a cell pass.

All raw roots, original failure cohorts, release build and original historical
512 inputs are indexed in `raw-evidence.json`. Public canonical files exclude
private authority fixtures. Checksum indexes detect corruption, not remote
attestation. Startup/observer changes do not establish sustainable admissions,
forwarding throughput, physical-core efficiency, a hardware ceiling, a qualified
soak or external-server validation. The historical Windows admission bottleneck
is not resolved by this Linux startup finding.
