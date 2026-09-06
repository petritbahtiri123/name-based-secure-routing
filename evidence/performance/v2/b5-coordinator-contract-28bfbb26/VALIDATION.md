# Coordinator and resource-bound validation

Source base28bfbb26. Test-only Rust coordinator; no live paced traffic claim.
Literal RED before implementation;25 Rust B5 tests and20 Python resource tests PASS.
Release Clippy --bin perf_rust_source --tests -D warnings PASS.
Repository-configured cargo fmt and scoped Ruff/check/format PASS.
Focused review: one Important sampler-exit coverage finding, RED regression then
fix; scoped re-review closed it and found no Important coordinator issue.
Live caller must check require_running=True, install failure guards and only
acknowledge final publication after successful output. Async wake/transport
integration and calibration remain pending. No protocol/security change.
