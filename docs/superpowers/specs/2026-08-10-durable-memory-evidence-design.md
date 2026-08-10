# Durable Memory Evidence Design

## Scope

Close only the long-run memory evidence durability and child-cleanup blocker. Preserve all existing evidence and frozen benchmark, protocol, security, capacity, load, QUIC, channel, and stream behavior. The new path applies only to completion runs whose phase is `memory`; existing short benchmark paths remain unchanged.

## Boundary

Add a focused durable long-run runner between `run_performance_completion.py` and the memory load-cell command. The runner owns process-tree lifetime, incremental capture of request output and resource/runtime event output, bounded buffering, periodic durable flushes, counter reconciliation, and the terminal run manifest. The benchmark child continues to own request generation and NBSR behavior.

## Evidence flow

The child emits generated NDJSON events. Request records are appended to `raw.ndjson`; resource and runtime records are appended to their own NDJSON series. Each writer has a bounded queue and bounded flush interval. Flush performs a userspace flush and `fsync`, while normal and exceptional shutdown close every writer. Partial files are retained.

The terminal manifest records `completed`, `timed_out`, or `failed`, whether partial evidence is durable, cleanup attempts and verification, and literal counters for offered, started, completed, failed, timed out, and persisted records. Only a completed, reconciled run may be authoritative. Timeout and failure manifests always set authoritative PASS eligibility to false.

## Process cleanup

On Windows the runner starts the child in a new process group and terminates the full descendant tree. It waits for exit, escalates if necessary, and verifies that the root and discovered descendants no longer exist before finalizing the manifest. Cleanup failure is itself recorded and prevents authority.

## Testing

Literal RED tests run short synthetic child processes that emit real NDJSON files, spawn a descendant, time out, fail, or exit normally. Assertions inspect generated evidence, reconciled counts, terminal manifests, and live process state. They do not assert source text. After GREEN, deliberate short timeout profiles prove durable retention and summary regeneration before any 30-minute memory experiment begins.

## Evidence completion

New formal memory evidence is additive under a new root referencing the prior partial baseline, accepted capacities, and previous memory runs. Prior checksum files are bound and verified without modification. Direct uses the accepted 50% evidence plus one stable upper point below the invalid 75% point; Rust and Go use two stable loads as specified. Classification remains PASS, FAIL, or INCONCLUSIVE under the frozen methodology.
