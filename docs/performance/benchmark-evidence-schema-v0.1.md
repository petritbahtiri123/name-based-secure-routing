# NBSR Benchmark Evidence Schema v0.1

`manifest.json` closes the evidence inventory with SHA-256 digests and binds
the repository SHA, dirty state, benchmark schema, environment digest, command,
start/end time, and result. `environment.json` records OS/build, CPU topology,
memory, power plan, affinity, Rust, Cargo, Go, Python, and binary digests.

Raw files are UTF-8 NDJSON. Each line is independently parseable and contains:

- `schema`, `run_id`, `sample_id`, `repository_sha`, `dirty_tree`;
- `environment_digest`, `path`, `implementation_version`, `scenario`;
- `transport_sessions`, `service_channels`, `application_streams`;
- `request_concurrency`, `payload_bytes`, `offered_load`, `achieved_load`;
- all eleven duration fields defined by the design, using null when a boundary
  does not exist for the path;
- `success`, `error_type`, `error_stage`, `bytes_transmitted`, and
  `bytes_received`.

Writers append complete lines through a bounded queue. Queue overflow, writer
failure, an incomplete final line, duplicate sample ID, or submitted/written
count mismatch fails evidence validation. Failures are never filtered from raw
evidence. Exclusions retain the original sample ID, reason, reviewer, and raw
file digest.

Summaries are derived artifacts. A matched comparison key is exactly:

`environment_digest, topology, build_profile, payload_bytes, load_level,
connection_lifecycle, run_ordinal`.

Implementation and scenario map to comparison roles but cannot be silently
collapsed into the key. Cold NBSR matches direct-cold; warm-new-service and
warm-existing-service match direct-warm. Any mismatch makes overhead
calculation fail closed.

