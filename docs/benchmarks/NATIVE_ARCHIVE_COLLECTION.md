# Native lifecycle archive collection

The lifecycle coordinator accepts `--archive-collection` to retain complete
bounded TAR files and validate them without expanding thousands of marker files
onto the host filesystem. The default extracted-directory workflow is unchanged.

```sh
python -B -m scripts.performance.linux_native_lifecycle_run --config CONFIG.json --output EXTERNAL_FRESH_DIRECTORY --archive-collection
python -B -m pytest -q -p no:cacheprovider tests/performance/test_linux_native_archive.py tests/performance/test_linux_native_lifecycle_run.py tests/performance/test_linux_native_lifecycle_remote.py tests/performance/test_linux_native_pair.py
```

Archive mode retains `source.tar` and `destination.tar`, records each transfer's
SHA-256, size, transfer/load/inventory durations, and writes the normal aggregate
result only after all endpoint, peer, management-event and configuration gates.
The final coordinator index covers the retained TAR bytes. The endpoint and peer
indexes inside the archives still cover every original member. A TAR is not a
diagnostic subset or a substitute for complete validation.

The read-only adapter rejects unsafe paths, duplicates, links, sparse/special
entries, file/directory collisions, truncation, and the existing entry/byte-limit
violations. It stores bounded member bytes in memory (up to 512 MiB per archive);
allow for both archives and validator overhead when choosing a host. It does not
weaken checksums, marker cardinality, event binding or ownership checks. Checksum
evidence remains trusted benchmark evidence, not signatures or remote attestation.

On the October 9 Windows host, the retained 4096 source filesystem inventory took
35.32 seconds under profiling: 13.23 seconds opening files, 9.15 seconds reading,
and 6.63 seconds resolving paths. Reading the same source inventory from its TAR
took 0.86 seconds after 1.10 seconds loading. Both full endpoint and peer gates
completed in 6.40 seconds including both archive loads and duplicate gate checks.
This local comparison includes profiling overhead in the filesystem baseline;
it is not a general filesystem or throughput benchmark. Small 16-client archive
extraction was separately profiled at 0.14 seconds. The archive path avoids both
expansion and subsequent repeated small-file access; no antivirus attribution
has been established and no security settings were changed.

Keep three outcomes distinct: the original 4096 coordinator deadline stop,
the subsequent successful offline replay of its retained evidence, and any new
live coordinator result. Archive mode itself is not evidence that a run passed.
Single-host Docker results do not establish multi-host/WAN behavior or sustainable
capacity. Original evidence, including failed attempts, must remain unchanged.

## Explicit 8192 live-bundle preparation

The Python coordinator and Rust benchmark source permit 8192 only in explicit
live-bundle mode. Idle-bundle limits, pacing, authentication, admission windows,
all eleven ownership counters, marker cardinality and hold/cooldown gates remain
unchanged. This is harness support, not an 8192 pass or a capacity claim.

Complete collection retains the 10,000-entry default and the 4096 source's
20,000-entry allowance. Only an 8192 lifecycle run selects 40,000 entries for the
source (four marker families plus evidence) and 20,000 for the destination.
Explicit archive limits cannot exceed 40,000; the 512 MiB byte ceiling and all
path, type, collision, inventory and checksum validations are unchanged.

Live/failure FD observers and UDP-table parsing permit at most 16,384 entries,
allowing 8192 source sockets plus non-socket descriptors and incidental UDP rows.
These are in-process observation bounds, not OS descriptor, socket, memory or
network settings. Identity/race checks and exact expected-socket cardinality
remain mandatory. Raising these bounds does not grant an execution budget.

Before an 8192 trial, require a fresh host/guest RAM and commit-headroom preflight,
explicit sustained-pressure abort monitoring, disk guards, and a separately
approved runtime including cleanup. Preserve the 4096 baseline. At 100 starts/s,
offering 8192 alone needs 81.92 seconds; no completed trial under the existing
120-second total cap has been established. Do not start the large trial solely
because these parser tests pass.

Focused limit checks:

```sh
python -B -m pytest -q -p no:cacheprovider tests/performance/test_linux_native_live_8192.py tests/performance/test_linux_native_live_2048.py tests/performance/test_linux_native_live_4096.py tests/performance/test_linux_socket_ownership.py tests/performance/test_linux_udp_failure.py tests/performance/test_linux_native_archive.py tests/performance/test_linux_native_lifecycle_remote.py
```

The dependency-free Rust count policy has unit tests in
`crates/nbsr-transport/src/bin/benchmark_support/lifecycle_client_limit.rs`.
A production benchmark binary must be rebuilt from the recorded source snapshot
before using the new maximum; the previous 4096 binary remains unchanged.

The intermediate 6144 live-bundle count is also explicit. Its source collection
allows 30,000 entries and destination 15,000; all other gates stay unchanged.
The Rust live-count maximum already covers it. Fresh resource checks and a
small paired validation remain prerequisites for the authorized single trial.
