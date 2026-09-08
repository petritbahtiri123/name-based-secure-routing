# September 9 quality checkpoint: not globally green

The corrected release Linux Rust command (benchmark-harness, all targets,
no-fail-fast) passes 384 tests with zero failures and two existing ignored tests.
The initial restricted fixture image had no Go compiler/demo source context;
its 21 integration setup failures are retained. The rerun uses the installed
Go-capable image and complete required source fixture, with unchanged assertions.
Release clippy --all-targets -- -D warnings and cargo fmt --check pass.

Windows go test -race -mod=readonly ./... passes in the production client,
demo client, ISP adapter and independent interop peer modules. The independent
federation verifier module fails TestCheckedInPackage with an untrusted manifest
digest; all other packages in that module pass. go vet passes in all five modules.

The manifest/pin mismatch already exists at the continuation start SHA. It is
BLOCKED_ARCHITECTURAL because reconciling immutable package trust/versioning is
outside benchmark authority. No pin, frozen authority, assertion or fail-closed
check was changed. See docs/benchmarks/FEDERATION_PACKAGE_AUTHORITY_BLOCK.md.

The earlier full Python performance run passes 834 tests, with three existing
skips, after the focused fixture/inventory repair. Its logs and scoped Ruff,
dependency/privacy/integrity checks are in closure-checks-40d109a8. This checkpoint
does not close the unqualified sustained soak or establish a production ceiling.
