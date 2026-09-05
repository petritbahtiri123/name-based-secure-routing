# Immutable fixed-run artifact packaging

Measured r5 cause: Docker mounted the configured build-parent tmpfs with
`rw,nosuid,nodev,noexec`, despite the Compose options omitting `noexec`.
The copied Rust binary had mode `0500` and matched the original SHA-256, but
execution under UID 65532 failed with `PermissionError`, errno 13.
Raw mountinfo, mode/hash result, container inspect and checksums are retained in
`C:/NBSR-build/isp-exec-diag-r5/`. The image was
`sha256:e4bbb72b1bc2e1a811bc04c11bea736133701a662940926cec7475f1d9eae2c6`.
The diagnostic container was inspected and removed; no security option was relaxed.

Preparation now supplies validated run ID and private CIDR as build arguments.
The runtime image bakes both existing artifacts at
`/opt/nbsr-build/nbsr-demo/<run-id>/` with mode `0555`, plus the public fixed-origin
configuration with mode `0444`. The existing read-only root protects these files.
The build-parent tmpfs is removed; all other mount and capability controls remain.

Build metadata binds exact source SHA, run ID and canonical private CIDR. Every
supervisor role receives and checks those fields before using artifacts. Runtime
startup verifies directory containment, regular non-symlink artifacts and hashes
against the immutable originals in `/opt/nbsr/bin`; it no longer copies or chmods
executables. ISP-B compares its baked origin configuration with the required
configuration instead of writing it. Go's fixed-parent/run-ID/hash guards and
the connector's fixed target remain unchanged. Images are specific to the
prepared run and subnet, and cannot be silently reused with another identity.

Focused RED: missing identity validator and the old attempt to recreate an
already baked directory. GREEN: supervisor tests pass, covering identity
mismatch, existing-artifact verification, tampering and symlink rejection.
A fresh accepted-source image build and live isolation run remain required;
synthetic tests do not establish Linux executable permissions or live routing.
