# Partial metric preservation

Three source-side resources.ndjson files (one per repeat) passed strict numeric/enum schema validation and were preserved in source-metrics-partial.zip. Raw bytes686; exact sizes/hashes and container paths in manifest.json. ZIP membership,CRC and complete SHA256 readback verified. Original files/containers remain untouched.

The first attempt timed out on the first copy after6seconds work; handles released, zero payloads persisted. The cold-read attempt completed three copies then rejected the first destination diagnostics.ndjson on record count (zero or >10000); it stopped without relaxing validation. No destination file was persisted or archived; this is3/9 partial preservation, not clearance to delete the containers. Supervised attempts8.03s and7.43s, all command ownership released, no starts/removals.

Cargo resolution authorization plan is ready but unexecuted. No additional container work was performed after this schema blocker.
