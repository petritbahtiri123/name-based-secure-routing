# B3 acceptance-window diagnostic

Status: diagnostic control, not an adopted default or proven capacity improvement.

The matched marker-monitor series at d76cc302 reduces source polling CPU but all
ten 2048-bundle attempts still fail. B3 deliberately arms one `accept_one()` at
a time; that call waits for both an incoming connection and its TLS handshake.
A delayed handshake therefore holds the sole acceptance slot. This is a concrete
head-of-line mechanism, but its contribution to the observed failures is not yet
quantified. Destination drop snapshots alone do not provide that attribution.

`scripts/run_b3_v2.py --accept-window N` adds an explicit B3 diagnostic override.
Allowed values are1,2,4,8,16,32, no larger than the offered connection count, and
only for paced simultaneous Rust bundle workloads. The default remains one
armed accept. B4 keeps its existing window. Ambient overrides are rejected by
the runner so the workload manifest cannot silently omit a changed setting.
The server records the actual selected window before acceptance starts.

Each pending accept retains the existing rate-release gate and the unchanged
transport timeout. The window bounds how many can be armed together. Do not
restore the historical all-at-start deadline defect, increase timeouts, change
authentication/authorization, or report a passing diagnostic as production
admission capacity. All established session tasks remain concurrent as before.

Initial experiment: matched current-source release runs, window1 versus32,
2048 live/materialized bundles,100 starts/s,1second keepalive,one selected Linux
guest CPU,two source shards,guest-native markers. Five counterbalanced pairs,
preserving every failure. A decisive improvement would justify testing smaller
windows before choosing a default. If it does not help, retain the negative
evidence and do not promote the setting.

Verification: literal RED Python workload tests and Rust parser tests, then
focused GREEN tests, existing release-gate tests, release clippy/default build
check, scoped Ruff/fmt/diff and one focused review. Source snapshots now include
both new B3 helper modules; complete build archives remain authoritative.

## Matched result at c267837c (2026-09-14)

All five counterbalanced pairs completed and were preserved. Window 1 passed
one full lifecycle and failed four; window 32 failed all five. The passing
window-1 attempt returned all eleven owned-resource counters to zero and both
roles exited. One success does not establish repeatable 2048-bundle capacity.

| Diagnostic result | Window 1 | Window 32 |
| --- | ---: | ---: |
| Complete / failed attempts | 1 / 4 | 0 / 5 |
| Median active markers, including failed attempts | 1537 | 1741 |
| Median source handshake timeouts | 511 | 253 |
| Total source client-task failures | 0 | 286 |

The 286 task failures correspond to `ControlStreamFailed` in source stderr,
after the transport handshake while receiving the control envelope. Reduced
handshake timeout counts therefore do not establish a reliability improvement.
Keep the default window at 1. The serial acceptance mechanism is not proven to
be the sole cause of the remaining limit, and window 32 is not promoted.

Failure-only destination UDP drop counts range from 616 to 6251 for window 1
and 14957 to 25440 for window 32. Retained source sockets show zero drops.
These snapshots omit closed sockets and timestamps; they cannot establish
causality, host saturation, or the precise delayed stage. Active marker counts
are diagnostic progress, not stable capacity or sustainable admissions/s.

All 2310 child-index entries were verified after copying guest-native evidence
before removing the stopped experiment container. Canonical evidence:
`evidence/performance/v2/b3-accept-window-pairs-c267837c`; retained raw evidence:
`C:/NBSR-build/b3-accept-window-pairs-c267837c`. Canonical index SHA-256:
`c97d8565a1ee8daee81f62a0eb302c17b592d21177c30647715b3b0c9ec708cd`.

Next attribution candidate: preserve timestamps of existing lifecycle marker
files only after a failed workload has stopped. This is not yet implemented;
any resulting intervals must be labeled marker-publication timing rather than
exact transport-only latency. No additional timed observer is justified yet.
