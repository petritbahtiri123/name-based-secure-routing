# Go lifecycle completion: Windows release evidence

MEASURED: baseline dfc22f2c passed 17/18 cells; corrected 97e0ca06 passed
18/18 cells. Each cohort has three repeats of 16/32/64 streams, 16/32
channels and 50 same-process lifecycle cycles. Corrected accepted cells
completed 1,680/1,680 authenticated 1 KiB round trips, including 150/150
same-process cycles and 1,200 cycle round trips. All owned source/destination
processes exited successfully and all eight instrumented destination counters
were zero. The first-three private-memory CV rule required no extra repeats.

The baseline channels-32-r2 failed at destination wait_for_send_ack after the
Go peer completed its 32 responses and closed. This unfavorable valid attempt
is retained. The harness previously allowed peer close before destination send
completion. The explicit local completion barrier now waits for the unchanged
destination send-completion path before Go closes. No wire message, security
check, production transport library or deadline changed. The result supports
the ordering correction; it does not prove packet-level causation of the old
failure or universal reliability from three repeats.

RED/GREEN regression evidence covers stale/malformed markers, cancellation,
exactly-once peer close, opt-in mode and atomic completion publication.
Rust release server tests: 28 PASS; Clippy -D warnings PASS; Go interop race
tests and vet PASS; affected Python tests: 156 PASS, one SKIP. See retained
test commands/results for exact stage provenance.

DIAGNOSTIC: private bytes, handles, threads and Go runtime samples are retained
in analysis.json and raw cells. The source exits before its final cooldown:
49 source versus 50 destination cooldown cycles are measured. Source ownership
counters are NOT_MEASURED. Runtime sampling is not phase-aligned and its final
sample can precede the final operations. Do not infer allocations/op, an
isolated bytes/resource cost, a leak, allocator cause, observer neutrality,
stable admission capacity or a qualified long soak from these measurements.

Reproduce analysis from the repository root:

    python -B evidence/performance/v2/go-b3-completion-97e0ca06/analyze.py C:/NBSR-build

Raw roots and index hashes: raw-evidence.json. Canonical files: checksums.sha256.
Build commands, exact source SHAs, executed binary hashes, every attempt,
process exit codes, raw outputs and repeat decisions are retained in those roots.
