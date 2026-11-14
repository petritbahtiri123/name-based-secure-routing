# Exported updates (0.2)

Open http://127.0.0.1:8765 and choose **Updates**.

No live source is connected. The Lab reads only artifacts you explicitly import; it does not tail the benchmark directory or connect to the experiment owner. A direct source/exporter integration must be reviewed separately before activation.

## How to update the view

1. Obtain a reviewed snapshot from the owner of the experiment, without accessing its active files through the Lab.
2. Confirm the export contains only grouped progress/final records and no credentials, private TLS material, host identifiers or unrelated diagnostics.
3. Use **Import JSON / NDJSON**. The browser posts to the same local server, not an external service. Or run `python -m lab.cli path-to-reviewed-snapshot.ndjson`.
4. Open **Updates** and select the new snapshot. Other open dashboard tabs refresh local imports every ten seconds. Import receipt time is displayed separately from source-relative elapsed time.

Each import is independent and content-addressed. Duplicate bytes do not create duplicate observations. New snapshots do not overwrite older snapshots, and filenames are not treated as proof of shared run identity. Counts of snapshots are not counts of independent experiments.

## Accepted formats

- Original `nbsr-b5-grouped-progress-v1` / `nbsr-b5-grouped-final-v1` objects, one per NDJSON line. Only these record types are accepted in this release. Do not mix stdout diagnostics into this export.
- Optional JSON envelope `nbsr-performance-lab-snapshot-v1`, with `records` containing those unchanged objects and optional `metadata` containing only `label`, `implementation`, `payload_bytes`.
- Metadata `implementation` may be `direct-quic`, `rust-rust`, `go-rust`; this is a declaration, not verified executable provenance. Without it, the UI displays **Unknown path**.
- Payload can be 1024 or 16384 bytes. Without metadata or a final marker, reported rate can be plotted but its payload accounting is explicitly unverified.

See [the machine-readable contract](export-contract.json), also served at `/api/v1/export-contract`. Limits: 4 MiB artifact, 4096 records/lines, 64 KiB per NDJSON line. The export must start at window 1/source time zero; delta-only chunks are not merged. Large/long exports require a future reviewed chunking contract, not silent truncation.

## What the states mean

- **Partial snapshot:** no reconciled final result. The benchmark could be running, stopped or unreachable. No live status is inferred.
- **Final marker reconciled:** a final producer record matches counters and timing in the snapshot. This does not independently establish process cleanup or capacity.
- **Invalid evidence:** structurally readable data fails accounting, sampling, phase, sequence, overflow or final closure checks. Raw bytes and source counters remain inspectable; trend plots are suppressed.
- **Quarantined:** malformed/unsupported structures cannot be safely normalized. Exact raw bytes remain downloadable with a reason.

A syntactically cut-off final NDJSON line is retained as partial framing after complete progress records. Duplicate JSON keys, NaN, unknown schemas and invalid complete lines are never silently discarded. A truncated tail after a final marker makes the evidence invalid.

## Interpretation

Source counters stay distinct: offered, reserved, issued, completed, missed, unreserved_current. Issuance is not a measured execution-start boundary. Started and incomplete remain unknown. Partial missed slots are not all unstarted operations.

Window goodput is **bidirectional application payload**; it is separate from summary goodput per direction and NIC traffic. Sampled window p99 is plotted separately for each source interval; null windows remain gaps. Steady/mixed/drain windows are labeled; warmup is not part of this series. No interpolation, pooled p99 or ABBA improvement inference is calculated.

## Testing and limits

Synthetic fixtures exist only under tests and in an isolated QA database when explicitly running `python -m tests.qa_server --data <separate-test-directory>`. They are labeled SYNTHETIC UI TEST ONLY and never seeded into the user's data directory. Port 8766 is reserved for that test session; the delivered app uses 8765.

Future work: validated producer export identity, automatic safe export delivery, resource telemetry pairing, bounded long-run chunk ingestion and matched ABBA analysis. These are not activated by this release. Local access still relies on loopback binding; there is no authenticated remote hosting.
