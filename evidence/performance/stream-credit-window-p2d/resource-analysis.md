# P2D resource analysis

## Observed state and resource bounds

On the measured x86_64 Windows build, Rust `size_of` observations were 16 bytes
for one `CreditEpoch`, 56 bytes for `CreditWindowState`, and 128 bytes for one
`CreditWindowEntry`. The exact command and output are preserved in
`resource-layout-observation.txt`. The existing regression also activates
4,000 never-consumed channel windows and holds the window state to at most 64
bytes.

The 56-byte window state contains one current epoch, space for at most one
draining epoch, and one optional pending-refill epoch. It has no per-credit
object and performs no allocation per slot. A granted window provides 64 bits
of consumed-credit state. Current plus draining is the hard maximum of two
recognized epochs; pending refill is one scalar state and cannot queue.

The authoritative 300.1691775-second live soak completed 5,704,000 operations
through 89,125 refill windows. Every one of its 713 session shards reported
active-epoch high-water 2, final replay entries 8,000 of the exact 10,000 cap,
64 remaining credits, 125 refills, and zero errors. Across all 24 aggregate
cells, 1,270 shards, and 2,540 source/destination shard endpoints, every
`replay_limit` was exactly 10,000.

Observed process state remained bounded across the soak:

| Role | First shard working set | Last shard working set | Maximum | First private bytes | Last private bytes | Maximum |
|---|---:|---:|---:|---:|---:|---:|
| source | 10,231,808 | 10,211,328 | 10,371,072 | 3,256,320 | 3,366,912 | 3,678,208 |
| destination | 10,919,936 | 10,924,032 | 11,001,856 | 4,091,904 | 4,059,136 | 4,345,856 |

Both roles stayed at four threads. These are observed per-process peaks from
the Windows sampler, not an attribution of all bytes to credit state.

## Thousands-channel model (estimate)

The following is a static logical-storage estimate, not a heap measurement.
It adds the observed 128-byte channel value and the 16-byte `HashMap` channel
key: 144 bytes per active channel. It excludes allocator metadata, hash-table
control bytes, spare capacity, and the enclosing session structures.

| Active channels | Logical key + value bytes |
|---:|---:|
| 1,000 | 144,000 |
| 4,000 | 576,000 |
| 10,000 | 1,440,000 |

No estimate substitutes for a mandatory gate. The resource gate is supported
by the exact epoch/pending/replay bounds, the 4,000-channel regression, and the
observed five-minute live soak.
