# Native lifecycle private-stream coordinator

This runner automates the finite per-host lifecycle contract in
[EXTERNAL_NATIVE_LIFECYCLE_PEER.md](EXTERNAL_NATIVE_LIFECYCLE_PEER.md).
It is a functional admission/ownership test, not a throughput, sustainable
admission, same-process retention or soak benchmark. Real external physical
hardware and SSH execution remain separate validation gates.

## Prerequisites

- Two operator-supplied Linux hosts, Python 3.12+, the existing project Python
  dependencies, Git and `taskset`; identical clean measurement checkout and
  exact-SHA release build manifests/binaries on both hosts.
- Existing non-root SSH credentials and verified known-host entries. The runner
  requires `BatchMode=yes` and `StrictHostKeyChecking=yes`; it does not provision
  credentials, accept unknown host keys, modify firewall rules or discover hosts.
- Routable distinct IPv4 data-path addresses; source ephemeral bind, destination
  bind may use zero for an ephemeral UDP port. Firewalls must already allow the
  chosen test path. No private-origin exposure is needed.
- Identical disposable test TLS/service fixtures, distributed through the
  operator's private channel. Each role has its own fresh native-filesystem
  lifecycle directory containing only `00/`. Do not precreate start/release/ACK
  markers. Keep TLS keys outside the checkout and public evidence directory.
- Native Linux storage for TLS, lifecycle markers and endpoint output. Windows
  mounts materially affected previous diagnostic cells. Do not silently mix
  storage placement between matched arms.
- Fresh per-role output paths outside the checkout/private fixtures; writable
  parent directories. No concurrent run may share a lifecycle/output root.
- Enough free disk for retained evidence (transfer bound: 512 MiB per role).
  Keep at least 5 GiB local reserve for this campaign.

The per-host native runner checks topology/affinity and build/source provenance.
`cores` selects its existing physical-core-aware pool. A Docker/WSL guest CPU
selection is not proof of exclusive physical host cores.

## Configuration and command

Create a JSON file with this exact shape; replace host aliases, addresses,
absolute paths and the 40-character measurement SHA with verified values:

```json
{
  "schema": "nbsr-native-lifecycle-coordinator-v1",
  "source_sha": "REPLACE_WITH_FULL_MEASUREMENT_COMMIT_SHA",
  "count": 16,
  "rate": 100,
  "shards": 2,
  "source": {
    "transport": "ssh",
    "host": "nbsr-source",
    "checkout": "/srv/nbsr",
    "binaries": "/srv/nbsr-build/binaries",
    "build_manifest": "/srv/nbsr-build/build-manifest.json",
    "authority": "/srv/nbsr-private/tls",
    "lifecycle": "/srv/nbsr-private/cell-001/source",
    "output": "/srv/nbsr-evidence/cell-001/source",
    "bind": "192.0.2.10:0",
    "cores": 1
  },
  "destination": {
    "transport": "ssh",
    "host": "nbsr-destination",
    "checkout": "/srv/nbsr",
    "binaries": "/srv/nbsr-build/binaries",
    "build_manifest": "/srv/nbsr-build/build-manifest.json",
    "authority": "/srv/nbsr-private/tls",
    "lifecycle": "/srv/nbsr-private/cell-001/destination",
    "output": "/srv/nbsr-evidence/cell-001/destination",
    "bind": "192.0.2.11:0",
    "cores": 1
  }
}
```

From the matching checkout on the management machine:

```bash
python3 -B -m scripts.performance.linux_native_lifecycle_run \
  --config /srv/nbsr-private/cell-001.json \
  --output /srv/nbsr-collected/cell-001
```

The management host may also use Windows Python. SSH aliases support configured
ports/IPv6 management addressing; the benchmark data-path bind remains IPv4.
The optional `docker` transport is for explicitly owned fixture containers using
UID 65532. It does not prove external server behavior.

## Gates and retained output

Source preparation precedes destination listening. The coordinator transfers
readiness, requires both complete active sets, holds two seconds, releases the
destination before the source, waits for source ACKs and destination report
readiness, then applies the two-second cooldown. Each host independently checks
its own elapsed time; no foreign monotonic clocks are subtracted.

Both endpoint relays must exit zero after their completion events. Collection
requires this invocation's first validated live phase, so an early failure
cannot archive a preexisting unrelated directory. Without that proof, output
ownership is `UNCONFIRMED_OUTPUT_OWNERSHIP`; local stderr/management logs remain,
and the remote path is left untouched.

Tar collection rejects traversal, duplicate entries, links, sparse/special files
and oversized content. A complete checksum inventory must match before deleting
the duplicate working archive. Failed archives are retained. Checksums detect
corruption; they are not signatures, host authentication or remote attestation.

Passing requires independent outer endpoint and inner peer gates: exact phase
order/hold/cooldown, named active/release/ACK markers, live PID/epoch/executable/
socket identity, release provenance, matching fixture/workload, payload success,
zero final ownership, and no forced/failed peer. The resulting status is
`PASS_FUNCTIONAL_CONTROLLED_PAIR`; capacity remains `NOT_ESTABLISHED`.

Keep `config.json`, `management.ndjson`, relay stderr, `cleanup.json`, both
transfer records and complete endpoint packages, `result.json` or `failure.json`,
and `checksums.sha256`. Preserve every unfavorable valid cell. Use at least
three valid repeats per cell and five when CV exceeds 5%; these finite diagnostic
timings do not become stable capacity metrics merely through repetition.

## Failure and cancellation limits

Catchable cancellation closes private control stdin. A live endpoint treats EOF
as cancellation and delegates kill/reap to the existing owned process-group
cleanup. Local relay cleanup is bounded; forcing a relay does **not** prove
remote cleanup. Such output is `UNCONFIRMED`, never a passing lifecycle result.
Network partition, host loss and SIGKILL cannot guarantee delivery of EOF or
recover remote evidence; inspect the explicitly owned remote run independently.

The coordinator's management deadline is 120 seconds, post-run collection is
bounded to 60 seconds per role, and transport deadlines are unchanged. Do not
increase them, add keepalive or reduce payload/cardinality to conceal failure.
Slow external management may exceed the fixture's existing idle lifetime; retain
and classify that as a fixture/platform limitation rather than NBSR capacity.

Start at 16 bundles and progress through 32/64/128/256/512/1024 only when prior
cells are meaningful. The Python runner now exposes the Rust binary's existing
1024-client bound without enabling keepalive. At 100 offered/s the 1024 launch
span plus hold exceeds its existing idle contract. A separately declared 200/s
cell has a nominal 5.115-second launch span before the unchanged two-second hold;
it is a different workload and must retain its own repeats/failures. No production
ceiling, sustainable admission rate or independent-tenant count follows from this
finite fixture. The same test identities and one service are used across bundles.


## Optional explicit child CPU pools

Each role may set `"cpu_pool": [0]` (or another available CPU ID) alongside
`"cores": 1`. The pool must have exactly the requested core count, ascending
unique nonnegative IDs, inherited availability, distinct advertised physical
cores and a single NUMA node. Defaults are unchanged when omitted. Only the
owned Rust child uses this selection; controller/observer placement is unchanged.
The retained resource samples and pair gate verify actual affinity. Guest CPU
IDs/topology are not proof of physical host core allocation.
