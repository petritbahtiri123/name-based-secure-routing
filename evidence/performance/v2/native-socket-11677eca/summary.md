# Native live socket attribution: point-in-time validation

COMPLETE for the bounded live-binding subtask, not full B1 or funding closure.
Source 11677eca; fresh locked Linux release build reproduces the same three Rust
binary hashes. No production code, protocol, trust, crypto, timeout or mandatory
check changes. Optional observation is disabled by default and explicitly marked
in peer provenance and pair/cohort comparison identity.

Five counterbalanced Direct/NBSR pairs at 1 KiB, 64 streams, 1000 operations per
stream, depth one and zero warmup complete: 10/10 cells, 20/20 endpoint joins.
Both peers run as UID 65532 in separate internal Docker network namespaces.
Each live PID/start epoch/executable/FD/inode binding matches the corresponding
captured local address/port, with observation interval inside retained process
samples. All 80 wrong-PID/epoch/binary/port joins reject. All captures retain
markers, zero-loss checks and independent TShark IP-byte/packet reconciliation.
Full peer/cohort checksum and equivalence gates pass at five repeats.

Literal RED: nine missing-module failures, one observer-comparison failure and
one claimed-observer-without-proof failure. Final focused scope: 90 tests PASS;
scoped Ruff PASS. Missing permissions, zombie/PID reuse, changed executable,
network namespace or FD, malformed tables and absent matching bindings reject.
Up to twenty bounded observations use the existing resource sampling loop;
all unavailable attempts are retained, with no timeout extension or fallback.

The result is an observed live local socket binding, not exclusive/continuous
ownership of every packet, remote identity proof, cleanup proof, physical-NIC
measurement or established-phase separation. QUIC security/completion checks
remain separate and unchanged. The observer is not performance-qualified; no
throughput improvement, stable capacity or production speedup is inferred.
The prior ec255c18 uninstrumented cohort is preserved and not pooled with this
instrumented cohort. Larger shapes and other platforms are not recertified.
