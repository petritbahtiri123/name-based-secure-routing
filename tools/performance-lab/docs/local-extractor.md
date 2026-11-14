> Scope: component-level implementation notes retained from development. Historical test counts and verification paths below describe development evidence that is intentionally not distributed. See [current setup and delivery status](../README.md) for the integrated workflow. A standalone component does not start a collector.

# Local stdout extraction prerequisite

`lab/extractor.py` implements only the local extraction portion of the existing
[benchmark handoff](../README.md). It is not a collector or CLI and is
not connected to the running dashboard. It performs no network, filesystem,
process, timer, inbox or benchmark operations. No dependencies were added.

## Contract

`StdoutExtractor(source_identity)` owns one declared source prefix. The future
bridge supplies each byte chunk with its exact next `offset` and unchanged
`source_identity`. A different offset or identity permanently makes this object
unavailable. The object cannot independently verify remote inode/boot identity,
rotation, same-size rewrites, authenticated transport or reconnect continuity.
Those checks remain required in the future transport. An operator label is not
proof of source identity.

`append(chunk, offset=..., source_identity=...)` and `snapshot()` return:

- `artifact`: exact grouped progress/final NDJSON lines, preserving original
  spaces and LF/CRLF terminators, or `None` before the first grouped record.
- `raw`: exact accepted source bytes, including diagnostics and an unfinished
  final line. These bytes must remain private and outside the dashboard/inbox.
- `ledger`: total source hash/size, grouped artifact hash, consumed and pending
  byte counts, source byte ranges and hashes for each complete record, framing
  state and existing-adapter measurement validity. No diagnostic contents,
  paths, credentials or measurement timestamps are invented in the ledger.

Only the two existing grouped schemas enter the artifact. The reviewed
`nbsr-rust-ownership-v1` schema with `event=diagnostic` is recognized and excluded
with a ledger entry. This producer exists in the inspected publication checkout
`d6376d8`, `crates/nbsr-transport/src/bin/perf_rust_source.rs`. Another diagnostic
schema requires source review and a focused compatibility change; there is no
generic "skip diagnostics" escape hatch.

Unknown schemas, extra grouped fields, duplicate JSON keys, malformed complete
JSON, non-finite numbers, adapter arithmetic/type errors, non-UTF-8 bytes and all
bytes after final stop publication. LF and CRLF are the only record terminators;
bare CR inside a record is rejected, while escaped JSON `\r` stays content.
Blank complete lines are not silently skipped. The retained prefix
does not become an acceptable new snapshot after a failure. `retained_raw`
remains readable for private failure evidence; chunks exceeding the total
source-byte limit or conflicting with identity/offset are not incorporated and
must be retained separately by the transport when necessary. Line/record-limit
failures within that total cap retain captured bytes. Bounded in-order bytes from the declared source
are retained before post-final/closed rejection, whether received in the same
chunk as the final marker or a later chunk. After any extraction failure,
snapshot, append and finish remain unavailable; starting a new object is not
permission to relabel the same failed experiment.

Incomplete lines wait for a later chunk. `finish()` is an explicit owner closure,
not a timer or a reaction to silence/disconnection. It requires a newline-framed
final marker with no partial tail. A final marker does not prove process cleanup
or a successful measurement: semantic/accounting failures stay visible as
`measurement_validity=invalid` under the existing Lab adapter.

## Bounds and integration

The captured source is limited to 4 MiB total, 64 KiB per line including its
terminator, and 4096 complete source records. Excluded diagnostics count toward
all bounds. These limits can be stricter than the grouped-only artifact limits;
preflight the intended run rather than dropping diagnostics to fit.

There is deliberately no background watcher. A future reviewed bridge must keep
the source raw bytes and ledger outside the production inbox and atomically
publish each successful full grouped prefix to the existing exporter. On failure
it must expose unavailable/stale delivery, never keep resubmitting the old
snapshot as fresh. Existing feed checks still enforce per-experiment prefix
continuity and final closure. Bare extracted NDJSON has no declared
implementation metadata; do not infer it from filenames.

Still required: exact owner-approved source path/run identity, bounded transport
with independently verified identity and offset continuity, lifecycle/cleanup
proof, a real advancing-snapshot diagnostic, original-source/final reconciliation,
collector OFF/ON overhead qualification before comparative claims, and separately
approved protected remote access. Do not change benchmark stdout, observer
cadence, budgets, protocol or security settings to accommodate this module.

## Verification scope

Focused tests use synthetic records and temporary stores only. They cover exact
bytes and offsets, diagnostic exclusion, arbitrary chunk boundaries, existing
exporter/inbox compatibility, malformed and unknown inputs, final closure,
invalid-accounting retention and budgets. No synthetic fixtures are placed into
the user's production data or inbox. Current command results are recorded in
`docs/verification/2026-11-13-extractor/` and the implementation plan.

This is a software prerequisite, not proof of a connected live stream, remote
file identity, zero collector overhead or a benchmark performance improvement.

## Opt-in origin compatibility (2026-11-14)

`StdoutExtractor(identity, origin_record=True)` supports the reviewed fresh28
`nbsr-origin-monotonic-v1` preamble. This opt-in requires one origin before grouped
records. It validates the exact six known uint64 fields and the bounded origin
interval checks of the inspected baseline overlay. It retains exact origin bytes
and an `origin` ledger entry, excluding them from grouped chart bytes. The ledger
schema is `nbsr-lab-local-extraction-v2` in this mode. Default behavior and ledger
v1 remain unchanged. This is shape/order validation, NOT source authentication,
clock calibration or cross-host alignment.

Six new tests first failed with the missing opt-in argument. Full suite then
passed 120 tests in 6.32 seconds; log: verification/2026-11-14-capture/origin-full.log.
Independent review accepted source hash
7c938299739de43ecaeb1837c3e29a578ea5ab5daaea646dccc435b468cd4578.

Whole-campaign validity is distinct from grouped counter validity. Fresh28 has
complete source counters but overall INVALID_PARTIAL after a post-calibration
guard failure. Its retained preview is deliberately separate from the running
Lab store, marked historical and invalid; never replay historical windows as live.
