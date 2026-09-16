# B3/B5 attribution checkpoint, 2026-09-16

Scope: the requested first two work blocks only. This is not a campaign freeze.

## 1. Retained B5 analysis: COMPLETE

See B5_RETAINED_FAILURE_DIAGNOSTIC.md and the sealed
`evidence/performance/v2/b5-retained-91a88774` package. Five complete ten-minute
traffic trajectories are now analyzed, including every unfavorable result.
Four retain their original failure classification. All five have zero traffic
errors/timeouts and zero final owned resources. No accepted continuous soak
or stable-capacity claim is added.

## 2. Root cause and justified correction: PARTIAL / UNRESOLVED

The extended memory trajectories answer a narrower question: the last five
minutes do not satisfy the existing continuous-growth predicate, while small
resident increases persist in the source. FDs and thread counts remain fixed.
This narrows the failure to residency/allocation behavior rather than observed
FD/thread accumulation, but does not distinguish allocator retention from live
allocation growth. No production leak or bounded ownership claim is justified.

The p99 failure in repeat 4 occurs early, and is not present in its final
first/last-third comparison. The original failure is retained. Thirty-second
peer CPU averages do not prove a saturated physical core or identify the wait.
Previous mapping/interposer diagnostics identify a receive-buffer reservation,
but were not observer-qualified for causal performance attribution; see
B5_LINUX_MAPPING_DIAGNOSTICS.md. No prefaulting, relaxed gate or longer timeout
is applied to make this pass.

For 2048 bundles on one guest CPU, the latest completed series remains four
passes and one failure (2022 materialized, 26 handshake timeouts). Earlier
failure markers place most missing progress before connection publication;
the long failure interval averages approximately 0.800816 peer cores with
1430 retained destination socket drops. See B3_FAILURE_MARKER_TIMING.md.
Neither the average nor cumulative drops identifies the causal transport
function or excludes transient contention. The accepted repeatable 2048
scale remains scoped to two/four guest CPUs.

A fresh non-root capability probe in the existing runtime image attempted
only its own disabled software CPU-clock event. `perf_event_open` returned
EPERM. The process had no effective capabilities, seccomp mode 2, and
perf_event_paranoid 2. This proves that this profiling route is unavailable
in the current container configuration; it does not identify which permission
layer denied it or prove every profiling method impossible. No security policy,
container security option or host setting was changed. The interface semantics
are documented in the [Linux manual](https://man7.org/linux/man-pages/man2/perf_event_open.2.html).
Probe source, exact image and output are retained in
`evidence/performance/v2/diagnostic-access-20260916`.

No additional production optimization was made in this checkpoint. A diagnosis
is not a fix; block 2 must not be counted COMPLETE. The shared marker scanner's
remaining measured polling cost is a possible harness experiment, not a proven
cause of the residual handshake failure. A future change must first demonstrate
equivalent file/timeout/cancellation semantics and then pass matched live runs.
Allocator attribution likewise needs a qualified observer before an optimization.

## Remaining work count

One of the six original blocks is closed here. **Five remain**: the unresolved
part of block 2, post-fix boundary reruns, qualified 60--120-minute soak, final
validation/deferred environment work, and the final evidence/funding package.
These are work blocks, not five commands or guaranteed single iterations.
No new routine approval gate is introduced. This file is the user-requested
checkpoint before choosing whether to continue the later blocks.

Existing deferred Windows profiling remains in
ADMIN_REQUIRED_FINAL_VALIDATION.md. The Linux permission probe is not grounds
to request a second arbitrary elevated capture or disable seccomp. Native
server validation remains external work; Docker/WSL is not server evidence.
