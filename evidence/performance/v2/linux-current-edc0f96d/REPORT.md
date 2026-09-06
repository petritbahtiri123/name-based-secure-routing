# Current-source Linux build and partial benchmark execution

PARTIAL / DIAGNOSTIC. Source edc0f96d0be2ae089e559092cab8fce2de50aac8; Rust1.97.1 release; three native ELF benchmark binaries independently hashed. Docker Desktop guest, one selected guest-core representative,1group,32streams,1KiB,depth1; not dedicated physical-server evidence.

The initial 1000 offered/s,10-second CLI compatibility cohort stopped on Direct p99 drift. NBSR was not run; no replacement. This lower-rate functional diagnostic is not a substitute for the failed Windows near-ceiling workload.

The first finite-reference attempt retained Direct1.447095 Gbit/s valid, then NBSR failed before measurement because its compile-time CARGO_MANIFEST_DIR resolves runtime vectors under /work. The isolated runtime did not contain that tree. The minimal preparation correction mounts the exact Git-exported crates and vector tree read-only at /work, preserving fixture bytes/security and workload semantics. These benchmark binaries currently require their build-root fixtures; arbitrary binary relocation alone is not supported.

The corrected new cohort retained: Direct1.446802, NBSR1.829187, NBSR1.824561, Direct1.458522, Direct1.422445 Gbit/s, then the third NBSR attempt failed telemetry with PermissionError on /proc/230/fd. Five valid rows plus one invalid are preserved. No replacement, no accepted Linux reference, no strict-stable/sustained/server claim. Six final post-close reports (including the telemetry-invalid attempt) independently have all eleven counters zero. The FD cause remains UNRESOLVED; zero cleanup does not excuse missing telemetry.

Preparation failures are also retained: one CRLF shell-script launch failure, two Git clone ownership failures, and full-checkout temporary-space exhaustion. A self-contained Git bundle and sparse source checkout avoid changing global Git trust or deleting evidence. None of these preparation failures is a benchmark capacity measurement.

365 raw files, including archives, Git bundles, native binaries, source snapshots, failed attempts and successful raw rows, are retained at the root in raw-evidence.json. The raw index hash is679ce31f6d1e0b25b99401daed3c3dd69bcb5c5af4d6198b9cb4787f86d217da. Raw Git bundles remain local; the repository package carries selected records/logs and hash indexes. No production/protocol optimization in this stage. Relevant Python gates were verified in preceding implementation commits; this stage adds actual release build/execution and evidence only.
