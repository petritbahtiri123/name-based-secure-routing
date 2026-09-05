# Fixture registry packaging repair

The r4 runtime image was
`sha256:0c4bef1f7c2917f8f8b96df99ebf619d9b3d511c5b8678c72a79343d1289c22d`,
bound to source `b7df259b7a941bf13a6bb96a55e02ba62e373276` in
`C:/NBSR-build/isp-prepare-live-r4-20260906/manifest.json`.

Diagnostic evidence and checksums are retained at
`C:/NBSR-build/isp-authority-diag-r4/`. The missing-registry control
(`stdout.json`) exited 1 in approximately 50 ms, with empty child stdout/stderr
and only the idempotency lock file created. This was startup failure, not
argument exit 2 or a 45-second destination-readiness timeout.

`registry-control.stdout.ndjson` records the embedded caller filename:
`nbsr.local/client/nbsr-go-client@v0.0.0/internal/authority/enrollment.go`.
The existing `federationDevelopmentRegistryPath` takes four parent directories
from this filename, then appends `docs/protocol/registries/federation-v0.1-development.json`.
With `-trimpath`, that resolves relative to the demo working directory as
`nbsr.local/docs/protocol/registries/federation-v0.1-development.json`.

Supplying only the unchanged public registry at that path allowed the same
binary to remain running for five seconds and create bootstrap and runtime
admission files; SIGTERM then yielded exit 0. The control retained UID 65532,
read-only root and network mode none. Two read-only diagnostic binds supplied
the diagnostic script and public registry; a writable tmpfs held the test copy.
No credential contents were captured. Diagnostic containers were inspected and
removed by exact owned names; the retained image was not deleted.

The registry SHA-256 is
`ed880f236a2b4b5e11e281e58c540534e1cd27f7c752d3990291cf1be55c80d0`.
The Dockerfile now copies that exact repository file to
`/src/docs/protocol/registries/federation-v0.1-development.json` and omits
`-trimpath` only for the fixture authority/client binaries. Their build paths are
fixed under `/src/client/nbsr-go-client`; the untrimmed authority caller path
therefore resolves to `/src/docs` using the unchanged loader. Adapter and origin
connector builds retain `-trimpath`. No production loader, registry contents,
trust, signing-purpose or wire semantics change.

The negative/positive runtime control proves the missing packaging dependency.
The revised image still requires a fresh accepted-source build and live
isolation run; neither is claimed complete by this repair note.
