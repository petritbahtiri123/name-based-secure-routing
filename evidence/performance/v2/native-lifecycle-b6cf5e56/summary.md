# Native namespace materialized lifecycle bundles

MEASURED functional scale at b6cf5e56: 16, 32, 64 and 128 concurrent bundles,
five repeats each. All twenty cells succeed: 1200 completed connections,
with one authenticated session, channel and materialized application stream
per bundle. Every source socket and the destination listener are observed under
live PID/start/executable/FD/inode identities on distinct internal Docker IPs.
All source and destination final eleven-field ownership checks are zero.

Each role runs as UID 65532 with observed affinity and process resources.
Source uses two existing runtime shards, a 100/s finite offered schedule and
unchanged security/idle/handshake/ACK behavior. Both named endpoint active
markers are required for every bundle before release. Hold is at least two
seconds plus the external socket-observer calls. This is not timing-qualified,
not sustainable admission capacity and not independent physical-host evidence.

Sampled median peak process RSS at 128 bundles is 50.75 MiB source / 44.375 MiB
destination. This includes the complete fixture/runtime and all coupled
resources; it is not an isolated bytes-per-connection/session/channel estimate.
Peak source FDs track the open sockets; observed thread counts and complete
trajectories are retained. Process exit alone is not the ownership proof.

Private benchmark credentials remain outside published raw roots. Post-run
public certificate copies/hashes are retained separately, without claiming
remote attestation or immutable pre/post authority measurement. The benchmark
fixture is trusted; this campaign is not a private-key-isolation security test.

The exact role/coordinator scripts, commands, source/build binding, marker
snapshots, socket identities, outputs and complete checksums are retained.
Windows controller monotonic timestamps are not directly comparable with Linux
process clocks; each socket interval is checked within its own Linux process
observation interval. No production optimization or hardware ceiling is claimed.
