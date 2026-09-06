# Benchmark explicit IPv4 bind verification

Implemented in the working tree, not committed. Read base-sha.txt and the copied
source/ files with this package's checksums to identify the exact patch tested.

Literal RED: parser-red.txt (missing external_bind module) and transport-red.txt
(missing benchmark_connect_from export), both exit101 before implementation.

GREEN: parser7; explicit transport4 + existing channel binding4/config8/handshake11;
existing UDP2. Total36 focused tests. Release Clippy for source/Direct/destination
with -D warnings PASS. No-feature release library/3binary check PASS with existing
nonbenchmark warnings retained in its raw log. Rustfmt2024 and scoped diff check PASS.

Flags: --benchmark-client-bind concreteIPv4:0; --benchmark-listen concreteIPv4:port
(including kernel-assigned port0). The existing ready output reports actual bound
listener address. Absent flags preserve loopback and wp8's legacy capture port.
Any explicit listener with a capture-port override conflicts. Separate NBSR
lifecycle harness rejects an explicit client bind rather than ignoring it.

Only benchmark-harness exposes benchmark_bind/benchmark_connect_from. Public
connect retains its signature/default bind and delegates to the same private
connection routine. Peer policy, TLS peer DNS name, exact SAN, ALPN, mTLS,
connection capability, channel exporter, ACCEPT, payload checks and ACK/close
semantics remain unchanged. No socket privilege or receive-buffer changes.

Tests are local loopback/argument/security checks. No external interface, remote
host, native two-host benchmark, Linux portability or performance result is claimed.
Directed subnet broadcast detection requires interface/netmask context; this
parser rejects the limited broadcast address and does not invent subnet metadata.

Live address diagnostic: four cells PASS (Direct/NBSR x default/explicit).
Listener ready addresses and owned-source Get-NetUDPEndpoint observations
prove127.0.0.1 defaults and127.0.0.2 explicit binds. Both processes exit0
in eachcell; all five payload-integrity/error fields zero. Four NBSR
post-close reports each contain11 current counters, allzero. All owned
processes joined. Direct receives completionACK aftersourceexit; the existing
NBSR P2A branch does not wait for it (bookkeeping only). No throughput or
external-host acceptance claim: socket inspection is an observer diagnostic.
