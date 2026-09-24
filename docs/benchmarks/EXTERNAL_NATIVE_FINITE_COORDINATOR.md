# Native finite forwarding coordinator

This executable adapter coordinates the existing 3-second warmup and 20-second
finite Direct/NBSR peer workload. It is a prerequisite for native reference work,
not a qualified paced soak or stable-capacity classifier. Actual independent-host
SSH execution is NOT_RUN. Docker namespace checks are guest/lab evidence only.

Build the three release benchmark binaries from the same clean source SHA on
both peers; preserve source/toolchain/build commands and the hash manifest. Use
the existing native peer runbook to provision private test TLS files outside the
repository and output roots. Never place private keys under an evidence root.
Preconfigure SSH aliases and trusted known_hosts without disabling host-key checks.

Create a controller configuration (replace SHA and explicit host/path/address
values with the installed environment):

```json
{
  "schema": "nbsr-native-finite-coordinator-v1",
  "source_sha": "FULL_40_HEX_SOURCE_SHA",
  "path": "nbsr",
  "payload": 16384,
  "streams": 8,
  "depth": 1,
  "source": {
    "transport": "ssh", "host": "nbsr-source", "checkout": "/srv/nbsr/source",
    "binaries": "/srv/nbsr/bin", "build_manifest": "/srv/nbsr/build.json",
    "authority": "/srv/nbsr/private/tls", "output": "/srv/nbsr/evidence/source-r1",
    "bind": "192.0.2.10:0", "cores": 1
  },
  "destination": {
    "transport": "ssh", "host": "nbsr-destination", "checkout": "/srv/nbsr/source",
    "binaries": "/srv/nbsr/bin", "build_manifest": "/srv/nbsr/build.json",
    "authority": "/srv/nbsr/private/tls", "output": "/srv/nbsr/evidence/destination-r1",
    "bind": "192.0.2.11:0", "cores": 1
  }
}
```

From the matching repository checkout on the controller:

```sh
python -m scripts.performance.linux_native_finite_run --config /absolute/config.json --output /absolute/new-controller-output
```

Use equivalent Direct/NBSR configurations and fresh outputs for each cell, with
counterbalanced order, minimum three repeats and five for CV above 5%. Preserve
all unfavorable valid attempts. No controller task changes firewall rules, network
policy, credentials, host keys or transport deadlines. Docker transport is a local
functional alternative using existing named fixtures under UID 65532.

The source controller first exclusively owns its root; this is not a completed
TLS/preflight event. Destination readiness is transferred over bounded private
JSON lines. Source native validation and a zero relay exit precede management ACK.
Direct's existing completion.ack controls peer lifetime. NBSR P2A already finishes
after its own stream ACKs, so its management ACK is stored outside the sealed peer
and does not alter send-completion semantics. Control endpoint waits remain inside
120 seconds; source readiness wait is at most 30 seconds. EOF/catchable cancellation
uses existing owned-child group kill/reap. Forced relays are never cleanup proof.

Retain config, management transcript, cleanup outcomes, both endpoint packages,
transfer hashes, failure records and complete checksum indexes. Collection is
forbidden without a validated live ownership event. Independent peer gates check
release build/SHA/hashes, workload, readiness, certificate hashes, process identity,
affinity and terminal samples. Checksums detect corruption, not remote attestation.

Optional config `"post_close_reports": true` requests existing NBSR post-close
reports on both roles. The coordinator independently binds each report to its
owned PID and requires all eleven live/entry counters zero. Direct retains its
process-exit scope. Omission preserves the original process-only mode. Five
matched Direct/NBSR functional repeats at ac40740c passed this gate; observer
qualification and long-run retention are not established by those trials.

Finite process exit alone is not an eleven-counter lifecycle/retention measurement.
CPU observations are lifetime totals, not steady CPU ns/op. Observer overhead and
host physical-core allocation remain unqualified. Do not load this package as a
B5 ceiling reference: observer qualification, reference classification, paced
coordination and its drift/resource gates remain separate unfinished work.

For a short **diagnostic only** paced pair, add `"diagnostic_rate": [1000, 1]`
and `"post_close_reports": true` to the configuration. The rational rate is total
offered operations per second for the single group, equal on Direct and NBSR.
Warmup remains three seconds, issue duration twenty seconds, progress windows five
seconds and controller cap 120 seconds. Use the same requested rate for matched
paths; this option does not derive or claim 70–80% of a qualified ceiling.

The transferred B5 transcript is bounded and independently checked with the
existing grouped accounting validator. `PACED_DIAGNOSTIC` reports achieved/offered,
goodput including drain, and retained drift failures; quantiles are medians of
steady-window quantiles, not pooled quantiles. Accounting validity does not mean
the offered load was sustainable. Live private-memory drift qualification and
qualified reference binding are absent, so this mode cannot replace a B5 soak.
