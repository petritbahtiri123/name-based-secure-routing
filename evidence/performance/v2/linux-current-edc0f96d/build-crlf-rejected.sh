set -eu
mkdir -p /work
tar -xf /evidence/crates.tar -C /work
rustc --version > /evidence/rustc-version.txt
cargo --version > /evidence/cargo-version.txt
CARGO_BUILD_JOBS=2 cargo build --locked --release --manifest-path /work/crates/nbsr-transport/Cargo.toml --target-dir /target --features benchmark-harness --bin perf_direct_peer --bin perf_rust_source --bin wp8_interop_server
mkdir /evidence/binaries
cp /target/release/perf_direct_peer /target/release/perf_rust_source /target/release/wp8_interop_server /evidence/binaries/
sha256sum /evidence/binaries/* > /evidence/binaries.sha256
