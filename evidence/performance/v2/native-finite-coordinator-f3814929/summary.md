# Controlled native finite forwarding and cancellation

MEASURED functional orchestration: source f3814929 completed five Direct and five
NBSR 16 KiB / 8-stream / depth-one cells in fresh Docker namespaces, 3 s warmup
and 20 s measurement. Both owned Rust peers select guest CPU 0. No physical host
core allocation, external SSH, NIC capacity, or stable ceiling is established.

DIAGNOSTIC medians: Direct 1.905323 Gbit/s (CV 15.98%), NBSR 1.929450 Gbit/s
(CV 21.71%). Median cell p50/p95/p99: Direct 0.964785/1.689365/2.678148 ms;
NBSR 0.964887/1.675629/2.848486 ms. All valid unfavorable runs remain included.
Dispersion and unqualified host/observer conditions prevent a strict-stable claim.
Background engineering activity was not isolated; these numbers are not an
optimization before/after result, a benchmark ceiling or a replacement scoreboard.

The initial source 0866ca47 cohort is retained: Direct 5/5 controller passes,
NBSR 0/5 controller passes although the independent native peer pair gate passes
all payload/exit records. NBSR finite mode naturally exits after stream ACKs,
while the new adapter incorrectly required controller ACK before return. RED/GREEN
fix f3814929 waits within the existing 120 s control deadline and places NBSR's
management-only ACK outside the already sealed peer. Direct's existing lifetime
ACK is unchanged. No Rust binary, timeout, keepalive, protocol or security change.
Three release binary hashes are identical across both exact-source builds.

Six catchable EOF controls (three source, three destination) pass. Each observes
both owned Rust PID/executable identities live under UID 65532, closes one private
control pipe, validates endpoint failures and owned-group cleanup, then separately
verifies the exact PIDs are absent before stopping fixtures. No local relay was
forced. This does not prove graceful eleven-counter cleanup, SIGKILL recovery,
network partition handling or inaccessible-host cleanup.

Legacy broad namespace scans may skip unreadable /proc entries and cannot alone
prove absence. Positive cleanup relies on owned-child terminal samples and reap;
EOF controls add the exact live-PID/absence test above. Source complete plus zero
relay exit precedes destination management ACK; retained events match the live
transcript. Archive collection requires a fresh ownership event and complete
checksums. Failed setup/network creation and all bad-valid cells remain retained.

Validation: 115 focused tests, literal RED tests for the new controls and early
NBSR exit, one focused independent review plus scoped fix review, Ruff, diff checks,
independent pair/transcript/ACK ordering and full privacy/integrity checks. Production
Rust/Go suites were not rerun for Python-only changes; release rebuilds preserve
identical Rust hashes. No exhaustive security recertification is claimed.

Cleanup after verified retention removed 20 stopped campaign-owned 0866ca47
fixtures (617,537,536 logical writable bytes) and their empty internal network.
Measured host free-space delta was -344,064 bytes; do not claim SSD recovery.
Source, raw evidence, build images and private test fixtures remain retained.

Reproduce analysis from repository root:

    python evidence/performance/v2/native-finite-coordinator-f3814929/analyze.py

See raw-evidence.json for retained complete source/build/test/command/endpoint
indexes. The runnable SSH/Docker configuration is documented in
`docs/benchmarks/EXTERNAL_NATIVE_FINITE_COORDINATOR.md`. Actual remote execution,
native reference runtime ownership, observer qualification, paced B5 drift/resource
checks and the 60/120-minute soak remain separate open tasks.
