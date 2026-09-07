# B5 sample storage preparation

The 8779e69c Linux fixed-rate diagnostic aborted on source-private growth after
10 seconds. Accepted diagnosis and raw checksums are retained in
`evidence/performance/v2/b5-sample-residency-8779e69c`. Reserved latency sample
storage gained resident pages as samples were written. Three optimized Rust
probe pairs measured 1 -> 24 pages without preparation and 48 -> 48 with it.

The benchmark now fills both bounded sample buffers before timing, observes the
fill through `black_box`, and clears their logical length. Capacity, sampling
stride, workload, deadlines, security checks and memory-growth gates are unchanged.
This shifts fixture residency to setup; it is not a memory-reduction claim.

Linux release RED: `collector_storage_is_resident_before_sampling` observed
1 resident page versus 2049 required. GREEN: the B5 binary test filter passed
51 tests with one existing ignored test. All-target Linux clippy with
`--features benchmark-harness -- -D warnings` passed. Rust fmt passed.
Execution logs and source snapshots are retained under
`C:/NBSR-build/b5-pretouch-17a4701f`.

Linux compilation also exposed a pre-existing misplaced descendant assertion in
`inheritable_sentinel` referencing an undefined variable, and a Windows-only
import without its cfg. The assertion is relocated to its lifecycle test,
retaining its original Linux scope. That focused Linux release test passed.
An exploratory extension of the assertion to Windows FAILED: the 100 ms timeout
completed without the descendant-started marker. This stronger Windows proof
remains INCONCLUSIVE; the timeout is not increased and no Windows descendant
coverage is claimed from that failure. The original Windows assertions remain.

Before/after fixed-load B5 reruns remain required. Passing unit tests does not
establish that all private growth is eliminated or qualify a sustained soak.
