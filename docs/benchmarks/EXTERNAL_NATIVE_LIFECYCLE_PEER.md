# Native Linux lifecycle peer

`python3 -m scripts.performance.linux_native_lifecycle` runs one owned release
peer on one Linux host. It preserves the existing materialized one-channel,
one-stream, 1 KiB lifecycle workload and bounded 120-second controller deadline.
It never changes transport timeouts, keepalive, buffer sizes or security rules.
Supported finite counts are 16/32/64/128/256/512, one or two source shards,
and one/two/four topology-selected guest-visible physical cores per role.

This is a functional scale fixture. Whole-lifetime latency includes the held
barrier and control delays; it is **DIAGNOSTIC_ONLY**, not admission capacity.
Per-role success requires exact cardinality, payload completion on the source,
and all eleven final ownership fields zero. A paired all-active hold is a
separate coordinator obligation; neither role alone proves it.

## Per-host commands

Use the clean native checkout, pinned dependencies, release build manifest,
fresh TLS authority and authenticated management channel from
[native peer execution](EXTERNAL_NATIVE_PEER_EXECUTION.md). The source SHA in
the manifest must equal each current checkout. Preserve private keys outside
evidence. Both hosts need identical public TLS/service fixtures; do not expose
the control directory to untrusted processes. Generate the existing service
fixture with `scripts.performance.authorities.write_authority_set(path, 1)`
and distribute it over the existing authenticated channel.

The variables below are absolute local paths on the respective host. `LIFECYCLE`
is a fresh control/service directory, separate from `RUN` and TLS `AUTHORITY`.
Its initial contents may only be the `00` service fixture and the declared
`connection-N.start` markers. Reusing a failed/finished fixture is rejected.

Destination:

```bash
python3 -m scripts.performance.linux_native_lifecycle \
  --role destination --binaries "$BIN" --build-manifest "$BUILD_MANIFEST" \
  --authority "$AUTHORITY" --lifecycle "$LIFECYCLE" --output "$RUN" \
  --bind "$DESTINATION_IPV4:0" --count 16 --shards 2 --rate 100 --cores 1
```

Transfer the complete, parseable destination `RUN/ready.json` to the source's
`READY_INPUT` over the authenticated management channel. It must identify the
expected destination IPv4 and unchanged `nbsr-quic-1` ALPN. Source:

```bash
python3 -m scripts.performance.linux_native_lifecycle \
  --role source --binaries "$BIN" --build-manifest "$BUILD_MANIFEST" \
  --authority "$AUTHORITY" --lifecycle "$LIFECYCLE" --output "$RUN" \
  --bind "$SOURCE_IPV4:0" --destination-address "$DESTINATION_IPV4" \
  --ready-input "$READY_INPUT" --count 16 --shards 2 --rate 100 --cores 1
```

## Coordinator contract and limits

1. Launch the destination, transfer readiness, then launch the source. Publish
   all named source `connection-N.start` markers; the source performs its existing
   finite offered-rate pacing. Do not burst-launch one process per connection.
2. Require every source `connection-N.active` and destination
   `destination-N.active` marker, with the declared materialized resource counts.
   Any failed marker or peer failure rejects the cell and preserves the prefix.
3. Hold all bundles for at least two seconds. Preserve live socket bindings
   under PID/start/executable/FD/inode identity if claiming native socket scale.
   These observers and management transfers are not timing-qualified.
4. Publish `connection-N.release` for every bundle in **both** role control
   directories (destination first, then source). The destination's existing
   materialized-stream handler also waits on these markers before returning
   the held payload; transferring them only to the source cannot complete.
   Require every source
   `connection-N.ack` and destination `destination.report-ready`, then wait the
   existing two-second cooldown and publish `destination.report-release`.
5. Require both zero-exit wrappers, both valid result/index files, identical
   source/build/fixture/workload provenance, and final zero ownership. Preserve
   the active-marker and release/ACK inventories separately from private keys.

The coordinator must bound all SSH/SCP/control operations and finish within the
existing peer/transport budgets. Do not increase timeouts or add keepalive to
make a remote control plane pass. Management latency may invalidate this held
fixture on a distant network; classify that rather than NBSR capacity.

Failure/cancellation kills and reaps only the wrapper's owned child process
group and seals its partial evidence. When available, failure-only live UDP
counters are retained before cleanup. Process cleanup is not a passing runtime
ownership result. The observer cannot recover counters from closed sockets.

Automated two-physical-host barrier orchestration and remote failure testing
remain outstanding. These executable **per-host** commands do not claim a
complete unattended external B3 campaign. Shared-WSL namespace smoke results
remain separate from external hardware, same-process repeated retention and
sustained admission/soak validation.

At a401567d, three release smoke cells with separate role control roots complete
48 connections and zero final ownership. The first missing-destination-release
attempt remains rejected and preserved. See [validation evidence](../../evidence/performance/v2/native-lifecycle-peer-a401567d/summary.md).

## Read-only transferred-pair gate

After copying the complete peer output directories, run:

```bash
python3 -m scripts.performance.linux_native_lifecycle_pair \
  --source "$SOURCE_OUTPUT" --destination "$DESTINATION_OUTPUT" \
  --source-sha "$MEASUREMENT_SHA" --count 16 --output "$PAIR_ANALYSIS"
```

The output must be a new file outside both peer directories. The gate verifies
complete checksum inventories, role/source/build/binary/fixture agreement,
exact argv and environment, readiness transfer, PID epochs, monotonic resource
counters, affinity, terminal exit and raw payload/cardinality/ownership results.
It rejects forced/failed peers even if someone reseals their checksum indexes.
It does not authenticate a remote host or prove the coordinator's simultaneous
all-active hold, actual socket bindings, sustainable admission or performance.
Keep the independently retained marker/hold/socket evidence with the pair.
