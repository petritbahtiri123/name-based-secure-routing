# Native phase packet accounting

MEASURED packet-order windows in two Docker network namespaces on a shared
WSL host. Twenty of twenty cells pass: five counterbalanced Direct/NBSR pairs
for 1 KiB/64 streams and 16 KiB/eight streams; 1000 operations per stream,
depth one, zero warmup. Three release Rust binary hashes remain unchanged.

Every capture passes zero-loss, MTU, exact tuple, complete inventory and
readiness/terminal coverage gates. Three unique ordered phase markers divide
setup, stream validation/warmup, established work with postflight, and teardown.
All four windows independently match TShark packet counts and IP-byte sums.
Forty live local socket joins pass and 160 wrong identity/port controls reject.
Peer and five-pair cohort integrity/comparability checks pass for both shapes.

Established work includes mandatory untimed payload validation and the existing
100 ms ACK drain. These are packet-order windows, not pure timed-operation byte
accounting or exact semantic attribution of asynchronous QUIC packets. Values
and every unfavorable valid repeat are in paired-phase-accounting.json.

An earlier first-cell controller comparison failed because serialized JSON key
order was mistakenly treated as chronological phase order. Its capture and
failure are retained separately; a read-only correction reconciles that same
capture. The corrected predeclared campaign is fresh and does not pool attempts.

Timing is DIAGNOSTIC: the observer is not performance-qualified. These results
do not establish a production speedup, stable capacity, physical NIC overhead,
exclusive continuous packet ownership, or external server validation. They do
not close the full B1 program or funding freeze. No production/security/wire,
mandatory validation or benchmark timeout changes were made.

Focused regression scope: 114 tests PASS; scoped Ruff and diff checks PASS.
Literal RED logs are retained. Build/capture/source commands, complete PCAPs,
phase-control events, independent checks and all peer outputs remain in the
external raw roots with complete SHA-256 inventories.
