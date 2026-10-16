# October 16 reviewed harness and correctness evidence

This package adds the reviewed harness changes developed after base
`ad77d59754651fee449bb1d9c14a946f9f3b2d15`, selected from local snapshot
`47d2ae41df49fedd21768db5fa6be71377acebf3`. It includes bounded cleanup and
ownership diagnostics, explicit pinned debug correctness, adoption metadata
compatibility, offline diagnostic helpers, and task-tree accounting tests.

The adjacent candidate manifest binds the selected files to SHA-256 digests.
The metadata fixture and its assertion replace a personal account with an
example account. Their original digests remain in the manifest; the sanitized
fixture is not claimed to be the original executed observation. Historical
review records and their source hashes remain historical.

## Validation

On the final prepared content, Python 3.14 ran 239 focused harness tests and
59 affected peer/pair/endpoint/lifecycle neighbors successfully. The standalone
diagnostic suite passed 17 tests; the accounting suite passed five. These are
320 offline tests, not evidence of a supported-platform matrix or native
deployment. No Rust source changed or Rust build was performed.

An earlier run overlapped fixture sanitization and reported 238 passes and one
failure because a loaded old assertion saw the new fixture. After file writes
finished, the complete 239-test selection passed. The earlier failure remains
recorded rather than relabelled as a pass.

Content digests and whitespace checks passed. Scoped checks found no private-key,
provider-token, account-SID or known private infrastructure markers in outgoing
content. Pattern scanning is not proof that every possible secret is absent.

## Run07 evidence boundary

The public summary is at `../benchmarks/sphere-2026-10-16/run07-summary.json`.
Run07 completed 55,896 operations using one QUIC connection, two application
streams, 1024-byte payloads and depth one, with zero reported integrity errors,
zero endpoint exit codes, and independent workload/TLS cleanup confirmation.
It used debug binaries and colocated VMs on one physical host. This is
correctness evidence, not a throughput/capacity baseline. The binary-build
source and runtime-harness source remain separately identified. No higher-load
trial is included or claimed.

## Weekly scope still outstanding

This is a reviewed subset, not certification that all weekly work is published.
Forty-five additional task-workspace candidates and 162 top-level standalone
diagnostic files remain retained locally pending dependency, privacy and
operational review. They include deployment orchestration, reconciliation and
budget changes, proposal variants and original diagnostic evidence. Other
repository work, including KAR/recovery and additional local-handoff evidence,
still requires reconciliation against published content.

Credentials, authentication stores/configuration, TLS material, raw access and
infrastructure inventories, personal outreach, private patches, caches, binaries
and unreviewed archives are excluded. Original local files are preserved.
No VM, Docker, TLS-generation or benchmark action was performed by this
publication preparation. Publication does not authorize a future live trial.
