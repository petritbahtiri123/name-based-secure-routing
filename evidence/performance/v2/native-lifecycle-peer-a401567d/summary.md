# Portable native lifecycle peer validation

At a401567d, three fresh 16-bundle release cells pass: 48 successful connections,
three paired all-active holds, 51 live socket identity records
(16 source sockets and one destination listener per cell), and both peers'
eleven final ownership fields zero. Both roles run as UID 65532 on guest CPU 0 in distinct internal network
namespaces with separate lifecycle control roots. All three release binary
hashes equal the b6cf5e56 build. No production code changed.

The first integration attempt reached all sixteen active bundles but failed:
its coordinator copied release markers only to the source's separate directory.
The existing destination materialized-stream handler also requires those
markers. The rejected attempt, source failures, missing destination releases
and forced cleanup are retained. The corrected coordinator sends destination
then source releases without changing any deadline or payload semantics.
Three independent corrected cells form the accepted functional smoke cohort.

Literal RED retained twelve failed contract tests against unimplemented stubs.
The first GREEN caught a test's Windows path-format assumption; corrected to
Path's native representation without changing the assertion's meaning.
Forty focused command, ownership, cancellation, native-peer and UDP-observer
tests pass; scoped Ruff and git diff checks pass. No unrelated Rust/Go rerun
is claimed for this Python-only runner change.

Per-host execution is now portable and source/build/fixture bound. Separate
physical-host SSH/barrier orchestration, network timing qualification, sustained
admission and repeated same-process memory retention remain unproven. These
are DIAGNOSTIC_ONLY functional fixtures, not improved capacity or server results.

Six stopped campaign containers were safely removed after canonical/raw hash
verification. Their reproducible writable layers total 2,693,197,824 bytes;
no host SSD recovery is claimed because Docker's virtual disk did not shrink.
Private fixtures, bind-mounted evidence, images and volumes remain intact.
