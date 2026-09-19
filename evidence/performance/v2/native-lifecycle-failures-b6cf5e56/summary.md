# Native held-bundle scale failure

The first 256-bundle continuation after twenty passing 16..128 cells fails:
146 source and destination active markers, 110 HandshakeTimeout markers.
The planned 512 progression is not run. No release/ACK is published; cleanup
is forced process cleanup, not a passing resource-ownership result.

A separate single failure-only diagnostic uses identical binaries, counts,
source shards, offered rate, affinity and timers. After the first failure marker,
it observes live PID/start/executable/FD-bound UDP sockets: 256 source sockets
and one destination listener, with zero cumulative drops on both roles at those
snapshots. Closed sockets, earlier identities and precise drop timing are not
observed. This does not prove absence of every network or scheduling problem.
The diagnostic also fails; it is retained separately, not pooled as a replacement.

The first attempt's sampled cumulative CPU counters give a maximum conservative
upper bound of 0.43 application cores in one-second windows stepped by 100ms over
the first ten seconds. Endpoint accounting includes a two-tick margin per role.
This does not measure kernel IRQ work, host/VM contention or shorter spikes.
It does not establish a hardware ceiling or justify a production optimization.

Classification: UNRESOLVED transport-handshake-progress on this shared WSL host.
No buffer, timeout, protocol or security change is made. Prior Linux buffer
experiments already failed all six 2048 one-CPU attempts; repeating that fix
without new attribution is not justified. Further invasive local diagnostics
without observer qualification are PLATFORM_DIAGNOSTIC_LIMIT. Physical-host
attribution remains EXTERNAL_HARDWARE_REQUIRED. Two failures are not a qualified
capacity-boundary cell; the last repeat-qualified native held scale is 128.

Raw indexes retain commands, per-role trajectories, stderr, forced cleanup,
marker contents, container metadata and the exact failure-only observer.
Private fixture keys remain excluded. A packaging attempt incorrectly assumed
plain-text failed markers were JSON; this was an analysis error, not a new run.
