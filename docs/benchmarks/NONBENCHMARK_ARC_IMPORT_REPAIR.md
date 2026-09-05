# Non-benchmark lifecycle compilation repair

The retained security run `C:/NBSR-build/security-current-dfdf21fd` failed the
release admission command before test execution: `wp8_interop_server.rs` used
`Arc` at lines 2455/2456 while its import was restricted to `benchmark-harness`.
The raw proof is `raw/replayed_grant_ticket.stderr.log` (E0433).

The repair removes only the feature gate from the `Arc` import. Lifecycle
concurrency, materialized-mode selection and their callers already compile in
both configurations. Changing their gating would change availability; making the
required import unconditional preserves existing behavior. The `Mutex` import
remains feature-gated. No protocol, authority, payload, timeout or barrier behavior
changes.

Fresh focused GREEN with `CARGO_TARGET_DIR=C:/NBSR-build/security-campaign/cargo-target`:

```text
cargo test --locked --release --manifest-path crates/nbsr-transport/Cargo.toml --test admission invalid_or_replayed_requests_leave_no_channel_state -- --exact
cargo clippy --locked --release --manifest-path crates/nbsr-transport/Cargo.toml --features benchmark-harness --bin wp8_interop_server -- -D warnings
```

The admission test passes (1 test); benchmark-feature Clippy passes. Existing
warnings in other non-benchmark binaries were not changed. These checks do not
replace the full security campaign rerun or live Docker validation.
