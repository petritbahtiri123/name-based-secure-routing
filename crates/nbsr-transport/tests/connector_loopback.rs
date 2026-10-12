#![allow(dead_code)]
#[path = "../src/connector_cleanup.rs"]
mod cleanup;
#[path = "../src/connector_control.rs"]
mod codec;
#[path = "support/connector_loopback.rs"]
mod live;
#[path = "../src/connector_registration.rs"]
mod owner;

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
#[ignore = "explicit authorized loopback integration; requires prebuilt Go worker"]
async fn isolated_go_rust_control_registration() {
    live::run_matrix().await;
}
