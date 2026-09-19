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

For a complete fixed-shape comparison, additionally validate the declared cohort
with `scripts.performance.linux_native_cohort`. Place this JSON outside the sealed
peer directories, using actual transferred paths (relative to the JSON file or
absolute). List every attempt in execution order; do not omit failed attempts or
replace unfavorable valid repeats. The three-pair example is:

```json
{
  "schema": "nbsr-native-cohort-v1",
  "attempts": [
    {"path":"direct","repeat":1,"source":"direct-r1/source","destination":"direct-r1/destination"},
    {"path":"nbsr","repeat":1,"source":"nbsr-r1/source","destination":"nbsr-r1/destination"},
    {"path":"nbsr","repeat":2,"source":"nbsr-r2/source","destination":"nbsr-r2/destination"},
    {"path":"direct","repeat":2,"source":"direct-r2/source","destination":"direct-r2/destination"},
    {"path":"direct","repeat":3,"source":"direct-r3/source","destination":"direct-r3/destination"},
    {"path":"nbsr","repeat":3,"source":"nbsr-r3/source","destination":"nbsr-r3/destination"}
  ]
}
```

```bash
python3 -B -m scripts.performance.linux_native_cohort \
  --manifest /absolute/comparison/cohort.json \
  --source-sha FULL_REVIEWED_40_CHARACTER_SOURCE_SHA \
  > /absolute/comparison/cohort-analysis.json
```

If either path's first-three goodput CV exceeds 5%, retain those attempts and
append repeat four (NBSR then Direct) and five (Direct then NBSR). The validator
requires both paths to reach five; residual CV above 5% remains unresolved.
It reuses the complete per-pair integrity gate, rejects reused directories or
identical sealed evidence presented as new repeats, and checks common workload,
binary/authority hashes and recorded placement configuration. Any invalid pair
rejects the cohort; it is never silently filtered out of the statistics.

PASS_FINITE_COHORT_INTEGRITY certifies these checks only. It reports medians and
paired goodput deltas as finite diagnostic comparisons. Declared execution order
is not independently verified from cross-host clocks; the manifest cannot prove
that an operator disclosed every attempt. Same recorded configuration does not
prove dedicated physical hosts or observer neutrality. No strict-stable,
sustained, runtime-ownership or hardware-capacity acceptance follows.

## Fixed useful work for packet comparisons

The separate opt-in `--operations-per-stream 1000` is available on **both** peer
commands. Keep the same value, payload, streams and `--depth 1` on both hosts
and both Direct/NBSR paths. Accepted bounds are 1..10000 operations per stream.
This mode uses zero warmup and the binaries' existing fixed-operation path;
it does not run the default twenty-second measurement. The existing 120-second
controller bound, protocol deadlines, security checks and ACK sequence remain.
Missing or extra completed useful operations reject before any completion ACK.

Record this as a different workload from the historical timed finite cells.
The pair gate checks the declared mode, exclusive CLI bound and exact completed
count; the cohort gate requires five counterbalanced pairs for fixed work.
For 1 KiB/64 streams at 1000 operations, the useful request/response denominator
is 131072000 bytes; for 16 KiB/eight streams it is 262144000 bytes. Untimed
frame validation, connection setup and teardown are outside that denominator.
Zero warmup does not imply that a whole capture is established-phase-only.

This port supplies equivalent useful work, not capture ownership/readiness or
wire acceptance. Bind packet evidence separately and keep observer-on performance
diagnostic. No relay or phase-control endpoint is inserted by this peer wrapper.
