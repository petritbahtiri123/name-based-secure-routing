# Task 4d verification

Base SHA: `361c315038bbcdb45008876657ec9269e0aa82ae`.

## RED

- `python -m pytest tests/performance/test_mixed_connections.py -q`: 2 failed / 13 passed while lifecycle directory polling remained.
- Rust coordinator tests initially failed to compile because the coordinator/types did not exist.
- `cargo test --locked --manifest-path crates/nbsr-transport/Cargo.toml --features benchmark-harness --bin perf_rust_source writer_timeout_does_not_extend_runtime_shutdown_deadline -- --nocapture`: 1 failed. A 10 ms writer deadline still held runtime shutdown for 200 ms through `spawn_blocking(join)`.
- The post-review filesystem-failure gate test failed collection before `terminal_evidence_complete` existed; after implementation, exact marker names plus a failed source/writer exit are rejected.

## GREEN

- `python -m pytest tests/performance -q`: 236 passed in the final run. Pytest emitted a non-fatal Windows access-denied warning while removing its pre-existing `pytest-current` temporary link at exit; no test failed.
- `cargo test --locked --manifest-path crates/nbsr-transport/Cargo.toml --features benchmark-harness --bin perf_rust_source`: 20 passed.
- `cargo test --locked --manifest-path crates/nbsr-transport/Cargo.toml --features benchmark-harness --bin wp8_interop_server`: 7 passed.
- `cargo clippy --locked --manifest-path crates/nbsr-transport/Cargo.toml --features benchmark-harness --bins -- -D warnings`: PASS.
- `cargo fmt --manifest-path crates/nbsr-transport/Cargo.toml -- --check`: PASS.
- `ruff check scripts/run_b4b_mixed_connections.py scripts/run_b4b_v2.py scripts/performance/mixed_connections.py tests/performance/test_mixed_connections.py`: PASS.
- `python scripts/verify_wp8_repository_safety.py dependencies .`: PASS; original manifests unchanged.
- `python scripts/verify_wp8_repository_safety.py privacy .`: PASS, 98 scoped files.
- `git diff --check`: PASS before staging.

Seven coordinator tests cover expected IDs, duplicate/unknown rejection, exact terminal files, writer thread isolation, cancellation/timeout, real panic/cancel tasks, filesystem failure without outcome mutation, and bounded runtime shutdown.

One focused independent review found the missing Python source-exit validity gate; it was fixed with RED/GREEN and the scoped re-review found no remaining load-bearing issue. The final runner rejects evidence when the source/writer exits nonzero even if marker filenames are exact. This post-measurement gate-only change does not alter binaries, workload, timing, or the stored results: every final measured source exited successfully (a nonzero exit adds at least the requested client count to `errors`; every non-baseline final record has fewer errors than that count). Raw data was not edited.

## Release evidence

`CARGO_TARGET_DIR=C:\NBSR-build\task4d-target python scripts/run_b4b_v2.py --output evidence/performance/v2/b4b-task4d-361c315038bb`

The runner builds release binaries, stores their SHA-256 digests in `environment.json`, and captures all 34 repeats without concurrent test/build work. The final classification is FAIL/SATURATED because high-client cleanup is not fully closed; this is not a test-suite failure hidden as PASS.
