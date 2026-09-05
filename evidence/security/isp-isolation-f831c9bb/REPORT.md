# Scoped ISP private-origin isolation

MEASURED: three fresh Docker topology lifecycles at f831c9bb passed the exact
same authorized-body and isolation checks. Each lifecycle denied four direct
origin probes (client and ISP-A, DNS name and private IP). Origin counters
remained zero through these probes, then recorded exactly one connection and
one accepted request through the authorized secure path. The returned body
matched exactly. Destination process completion passed; teardown left zero
campaign containers, networks and volumes. Child logs were retained first.

Architecture: client -> ISP-A opaque non-frozen TCP adapter -> unchanged Go
client and NBSR QUIC path -> ISP-B opaque UDP adapter -> unchanged Rust fixture
backend launcher -> fixed Origin Connector -> private-only origin. Three
internal Docker networks; no published host ports. Nonroot, read-only,
capability-drop and no-new-privileges controls remained enabled.

MEASURED separately: federation admission preflight passed, including 37 Linux
Python tests and a fixture authorization/drain with zero active allocations.
Eight retained limit buckets are expected bounded bookkeeping.

NOT_PROVEN: live runtime federation between independent operators, adversarial
host/root resistance, independent authority secret isolation, WAN/server
performance, runtime ownership counters or comprehensive failure recovery.
The runtime uses shared test bootstrap material and fixture authority; this is
one logical topology on Docker Desktop Linux on a Windows laptop. Negative
reachability is supported by the successful authorized-path positive control.

The r6 failed predecessor is preserved. Its absent compiled manifest-directory
anchor made existing public attestation files inaccessible through Rust's
relative lookup. Adding the empty directory repaired packaging only; no Rust,
protocol, security policy or fixture bytes changed. Diagnostic RED/GREEN logs
remain at C:/NBSR-build/isp-vector-path-diag-r6. Earlier failed prepares and
runtime attempts remain external and are not successful isolation evidence.

External indexes bind complete raw command logs, inspections, child logs and
checksums. The canonical package contains summaries and references; it does
not contain authority credentials. No legacy demo evidence is substituted.
