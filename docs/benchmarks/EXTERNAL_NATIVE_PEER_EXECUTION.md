# Executable finite native-address peer

`python3 -B -m scripts.performance.linux_native_peer` replaces the untested
inline `observe.py` wrapper for the finite two-host procedure. It owns one peer
on one Linux host. It does not SSH, change network/security policy, transfer
private keys, synthesize remote ACKs or run the entire external matrix.

Use the source/build/manifest steps in EXTERNAL_LINUX_SERVER_VALIDATION.md and
the fresh role-specific authority transfer in EXTERNAL_NATIVE_TWO_HOST_RUNBOOK.md.
Both checkouts must be clean at the same reviewed SHA. Keep original build-path
fixtures available. The release manifest must bind the three exact binaries,
source SHA, build commands and toolchains. Remove inherited `NBSR_*` experiment
settings, including the build-only `NBSR_LINUX_BUILD_EVIDENCE` variable, before
invoking this driver. Do not change TLS DNS peer identities to IP identities.

Define these absolute paths and real preconfigured interface addresses on each
host: `BIN`, `MANIFEST`, `AUTH`, `RUN`, `SOURCE_IPV4`, `DESTINATION_IPV4`.
`RUN` is outside the checkout and private authority tree. Select a fresh
`CELL=direct-r1` or `CELL=nbsr-r1`; set `MODE` accordingly. The destination
command runs first and remains attached:

```bash
python3 -B -m scripts.performance.linux_native_peer \
  --role destination --path "$MODE" \
  --binaries "$BIN" --build-manifest "$MANIFEST" --authority "$AUTH" \
  --output "$RUN/$CELL" --bind "$DESTINATION_IPV4:0" \
  --cores 1 --payload 1024 --streams 64 --depth 1
```

Transfer its `ready.json` into a separate source-side input file using the
existing authenticated, bounded SSH/SCP procedure. Never disable host-key checks.
The source validates exact destination IPv4, nonzero port and `nbsr-quic-1` ALPN:

```bash
python3 -B -m scripts.performance.linux_native_peer \
  --role source --path "$MODE" \
  --binaries "$BIN" --build-manifest "$MANIFEST" --authority "$AUTH" \
  --output "$RUN/$CELL" --bind "$SOURCE_IPV4:0" \
  --ready-input "$RUN/$CELL.ready.json" --destination-address "$DESTINATION_IPV4" \
  --cores 1 --payload 1024 --streams 64 --depth 1
```

Only after the source command exits zero, `result.json` is PASS_FINITE_PEER,
`validated-result.json` passes the P2A contract, and no `failure.json` exists,
send the destination completion ACK using the runbook's bounded operation.
Do not treat the early appearance of a JSON file as authorization before source
wrapper exit: source/binary/certificate provenance checks and sealing must finish.
Direct's existing 30-second ACK deadline is unchanged. The single-group NBSR
server does not wait for this marker; do not add a marker after its evidence has
been sealed. Confirm both destination and source wrapper exit zero. Preserve
any failure and stop that cohort; do not replace a failed repeat.

Warmup is three seconds and the measured interval is twenty seconds. This
finite wrapper's out-of-band deadline is 120 seconds, matching the authored
runbook; it is not a configurable longer protocol deadline or a soak runner.
Core selection uses the existing one-NUMA, one-logical-CPU-per-reported-physical-
core selector. Every sampled thread must stay in the selected pool. Host/guest
scope and cgroup observations remain explicit; pinning alone proves no host bound.

Repeat three counterbalanced pairs per shape, expanding both paths to five
when either goodput CV exceeds 5%. Preserve residual dispersion. Repeat the
16 KiB/eight-stream shape separately with `--payload 16384 --streams 8` on both
hosts. Other supported finite depths and available core counts retain the same
equivalence rules. These finite repeats do not classify strict-stable capacity.

The wrapper writes exact argv/overrides, source/build/binary/certificate hashes,
host topology, stdout/stderr, PID, 100 ms resource samples, an unreaped terminal
sample, exit/result and a recursive checksum index. Runtime resource ownership,
steady-state CPU ns/op, NIC/IRQ/thermal behavior and observer cost remain separate
measurements. CPU totals include startup/warmup/drain. Never subtract monotonic
timestamps across hosts. Private keys are neither copied into nor hashed in the
publishable output. Forced cancellation kills only the exclusively owned process
group and rejects the attempt; it cannot produce an accepted source result.
The CLI defers SIGINT/SIGTERM/SIGHUP requests to owned-process safe points,
including across process creation, so interruption cannot lose the newly spawned
peer before cleanup. Repeated catchable signals do not interrupt that cleanup.
SIGKILL, host failure and kernel failure cannot be handled by a Python controller;
use the existing operator-owned container/service lifecycle for those cases.

This implementation is a finite per-host subset. Two-container execution, if
retained, verifies native-address transport and orchestration across namespaces,
not independent physical hosts, WAN behavior, server scaling or production
isolation. External hardware acceptance and the full admission/resource/soak/wire
matrix remain separate gates.

After transferring both complete sealed peer directories, verify their join
without rerunning or rewriting raw evidence:

```bash
python3 -B -m scripts.performance.linux_native_pair \
  --source /absolute/copied-source-cell \
  --destination /absolute/copied-destination-cell \
  --source-sha FULL_REVIEWED_40_CHARACTER_SOURCE_SHA
```

Run this once per Direct/NBSR cell. It rejects incomplete or changed checksum
inventories, mismatched source/build/workload/CA/readiness, wrong executed
binaries or command shape, failed exits, inconsistent process identity/CPU
counters and forced-cleanup attempts. A success is PASS_FINITE_PAIR_INTEGRITY.
Checksums are not signatures, authenticated transport or remote attestation;
retain the authenticated transfer and host custody procedure. The gate does
not establish observer neutrality, runtime ownership cleanup, external hardware,
steady-state CPU cost or strict-stable capacity. Do not subtract timestamps
across the two hosts. Its JSON report goes to stdout, outside the sealed roots.
