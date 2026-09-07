# B3 source provenance preflight

Two synthetic RED tests demonstrated that tracked edits or untracked source
could still produce B3 metadata marked MEASURED_PENDING_ANALYSIS. Retaining a
patch alone did not prevent that classification, and untracked source was not
represented by the patch.

The runner now requires an empty Git status, including untracked files, before
creating evidence or discovering the platform. It records that status with the
source SHA. Explicit older-binary diagnostic classification is unchanged.
This does not change workload, telemetry, authority, protocol or timeouts.

Validation:2RED tests;42focused B3 Linux runner/capture/analysis tests PASS;
Ruff PASS. Raw logs/source snapshots are indexed in
`evidence/performance/v2/b3-source-preflight-1c16b03d`.
Earlier actual1c16b03d runs used a fresh isolated checkout and remain bound to
that recorded source. This new preflight must not be retroactively claimed as
having run in their older controller.
