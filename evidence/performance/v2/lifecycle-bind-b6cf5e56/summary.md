# Explicit lifecycle source bind prerequisite

MEASURED Linux loopback-alias mechanics at b6cf5e56, not external hardware or
capacity. Three default and three explicit 127.0.0.2:0 cells each complete two
same-process cycles: twelve cycles with all eleven ownership fields zero.
Twelve live PID/start/executable/FD/inode socket snapshots confirm the expected
source address during active work. The 0.0.0.0:0 negative case fails before
active work; its failed evidence remains retained, not replaced.

Literal live RED uses release 2c35c773 while the checkout parent is c7ca8651:
explicit lifecycle bind aborts at its unsupported-mode guard. The initial
controller checked wrapper stderr rather than the retained child stderr; the
corrected read-only assertion confirms the exact child panic. No failed
controller output is treated as a passing benchmark.

The lifecycle path now uses the existing feature-gated benchmark connector.
Default loopback placement, TLS identity, ALPN, endpoint/service policy, replay,
timeouts, close and ACK semantics remain unchanged. Production builds continue
using the production connect entry. This is a harness portability change, not
a production optimization or an admission-rate improvement.

Seven source bind argument tests and four authenticated transport tests pass,
including wrong ALPN/name rejection and authenticated channel binding. Linux
release feature-enabled clippy -D warnings and Rust fmt pass. The non-feature
source build check passes with seventeen warnings; it is not claimed lint-clean.
No full new-source adversarial certification is inferred.

The regression fixture injects only the explicit CLI argument and a separate
live socket observer; both launchers and exact commands are retained. Timings
are diagnostic and these records are not a capacity comparison. Remote
lifecycle/admission readiness, barriers and telemetry remain separate work.
