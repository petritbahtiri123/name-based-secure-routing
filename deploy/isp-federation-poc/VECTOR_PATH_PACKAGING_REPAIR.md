# Manifest-relative fixture vector lookup

The r6 isolated run at `2ae59bab7593f5f2982582acf34f0aa760f09d94`
passed federation preflight and four denied direct-origin probes, then failed
the authorized workload with destination `StreamFailed`. Its raw evidence is
retained at `C:/NBSR-build/isp-isolation-live-r6-20260906`; overall status is FAIL.

The unchanged Rust demo fixture opens local admission attestations through
`CARGO_MANIFEST_DIR/../../vectors`. In the Linux build this is
`/src/crates/nbsr-transport/../../vectors`. The runtime contained `/src/vectors`
but not the intermediate manifest directory. Linux cannot traverse the missing
components even though the lexically normalized target exists.

An actual nonroot, read-only, network-disabled r6 image probe failed for both
compiled paths while canonical files existed. Adding only the empty manifest
directory made the same probe pass with identical canonical bytes. Raw RED,
GREEN and build logs are in `C:/NBSR-build/isp-vector-path-diag-r6`. The first
diagnostic build used an unsupported bare image ID in FROM and is retained;
the retry used a local tag of that exact image.

The runtime Dockerfile now creates the empty directory and checks both lookup
paths against canonical bytes at build time. No Rust code, vector, authority,
protocol or runtime security setting changes. This establishes the packaging
defect and its repair; complete live-path success still requires a fresh run.
