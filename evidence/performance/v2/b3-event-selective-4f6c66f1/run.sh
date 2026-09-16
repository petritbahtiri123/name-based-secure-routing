#!/bin/sh
set -eu
mkdir -p /work
tar xf /evidence/crates.tar -C /work
cp /evidence/event_monitor.rs /evidence/gate.rs /work/crates/nbsr-transport/src/bin/b3_support/
printf '\nmod event_monitor;\n' >> /work/crates/nbsr-transport/src/bin/b3_support/mod.rs
cat /evidence/probe.rs >> /work/crates/nbsr-transport/src/bin/b3_support/mod.rs
cd /work
rustc -Vv
cargo -V
CARGO_BUILD_JOBS=2 cargo test --offline --locked --release --manifest-path crates/nbsr-transport/Cargo.toml --target-dir /target --features benchmark-harness --bin perf_rust_source b3_support -- --nocapture
lscpu -p=CPU,CORE,SOCKET,ONLINE
taskset -c 0 cargo test --offline --locked --release --manifest-path crates/nbsr-transport/Cargo.toml --target-dir /target --features benchmark-harness --bin perf_rust_source event_monitor_cpu_comparison -- --ignored --nocapture --test-threads=1
