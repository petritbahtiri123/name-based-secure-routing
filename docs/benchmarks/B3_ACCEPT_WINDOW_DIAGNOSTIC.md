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
