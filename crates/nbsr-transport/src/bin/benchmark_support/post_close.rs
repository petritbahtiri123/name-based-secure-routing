//! Optional benchmark evidence only; capture after run-local handles are dropped.
use std::fs::OpenOptions;
use std::io::Write;
use std::path::{Path, PathBuf};

pub(crate) fn prepare(path: Option<PathBuf>) -> Option<PathBuf> {
    if path.is_some() {
        nbsr_transport::diagnostics::enable_global();
    }
    path
}

pub(crate) fn write(path: Option<&Path>, role: &str, runtime_state: &str) {
    let Some(path) = path else { return };
    let ownership = nbsr_transport::diagnostics::global().snapshot().json_line(
        role,
        0,
        "post_run_handles_dropped",
    );
    let mut file = OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(path)
        .expect("new post-close evidence file");
    writeln!(
        file,
        "{{\"schema\":\"nbsr-p2a-post-close-v1\",\"pid\":{},\"role\":\"{role}\",\"diagnostics_enabled_before_run\":true,\"runtime_state\":\"{runtime_state}\",\"ownership\":{ownership}}}",
        std::process::id()
    )
    .expect("write post-close evidence");
}
