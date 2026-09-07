# B3 1024-bundle retained failure analysis

Follow-up: [B3_IDLE_ATTRIBUTION.md](B3_IDLE_ATTRIBUTION.md) records three new
matched-workload attempts with complete close reasons. Idle expiry is now
proved for their `timed_out` connections; the historical analysis below keeps
its original evidentiary limits.

DIAGNOSTIC, not a new benchmark or causal proof. Workload source `d0792699`.

The retained source output contains exactly one outcome for each of 1024 client
IDs: 791 successful application rows and 233 `client_task_failed` rows. All
failures are IDs 0–235, except successful IDs 230, 232 and 234. The source log
has 233 failures at `perf_rust_source.rs:617` (send-and-receive) and 233 parent
join failures at line 745. Destination has 233 application-accept failures at
`wp8_interop_server.rs:2485`. They precede successful lifecycle completion;
the controller's ACK-file timeout is a downstream symptom, not evidence of a
wire ACK implementation bottleneck. Successful application rows alone do not
qualify full lifecycle cleanup or a valid 1024-bundle cell.

The controller schedules bundles at 100 starts/s. Across 1024 clients this
spans approximately 10.23 seconds. Retained resource samples have an idle-to-
active gap of 10.281 seconds at source and 10.275 seconds at destination.
Source policy uses 30-second idle timeout; destination uses 10 seconds.
Successful scenario durations range from 2.224 to 10.082 seconds.

INFERENCE: waiting for the whole cohort before common release may let early
connections expire under the negotiated idle policy. Failure concentration in
early IDs supports this hypothesis. The sample gaps are not individual idle
durations, and the logs do not retain transport close reasons for this
non-materialized bundle path. Therefore idle expiry remains UNRESOLVED.
No timeout, keepalive, launch rate, workload, or production change is justified
by this review alone. Do not describe 512 as a hardware or NBSR ceiling.

Next bounded diagnostic: capture categorized transport close reason plus
monotonic connection-ready/release/failure times on failure only for the
existing non-materialized path. Compare unchanged 512/1024 workloads and apply
the existing observer/repeat gates. Preserve the 10-second policy; do not
increase timeout or introduce keepalive merely to pass. If the hold workload
conflicts with its idle policy, document that validity constraint explicitly
before designing any separately labeled workload.

Reproduction (read-only, verifies selected inputs against the retained index):

```powershell
python scripts/analyze_b3_1024_failure.py C:/NBSR-build/linux-b3-joined-d0792699/bundles
```

Output is preserved in `evidence/performance/v2/b3-1024-retained-analysis` with
input SHA-256 bindings and a local checksum index. The existing canonical B3
package binds the complete raw index. Focused checks verify the complete ID
partition, outcome counts and rejection of modified input bytes. Ruff passes.
No performance gain or security change is claimed.
