# P2D resource analysis

## Observed state and resource bounds

On the frozen Attempt-8 x86_64 Windows build, compiler layout observations
were 16 bytes for one `CreditEpoch`, 64 bytes for `CreditWindowState`, and 136
bytes for one `CreditWindowEntry`. The exact final-source command and output
are preserved in `resource-layout-observation.txt`. The regression also
activates 4,000 never-consumed channel windows and enforces the 64-byte state
bound.

The 64-byte state contains one current epoch, at most one draining epoch, two
compact assigned-stream counters, and one optional pending-refill epoch. It
has no per-credit object and performs no allocation per slot. A granted window
provides a 64-bit consumed-credit bitmap. Current plus draining is the hard
maximum of two recognized epochs; pending refill is one scalar state and
cannot queue. Retirement requires the draining epoch's assigned counter to be
zero.

The authoritative 300.3870077-second live soak completed 4,832,000 operations
through 75,500 refill windows. Every one of its 604 session shards reported
active-epoch high-water 2, exact replay limit 10,000, no more than 8,000 final
replay entries, and zero errors. Across all 28 aggregate cells, 1,363 shards,
and 2,726 source/destination shard endpoints, every measured `replay_limit`
was exactly 10,000.

Observed process state remained bounded across the soak:

| Role | First shard working set | Last shard working set | Maximum | First private bytes | Last private bytes | Maximum |
|---|---:|---:|---:|---:|---:|---:|
| source | 10,686,464 | 10,715,136 | 10,883,072 | 3,403,776 | 3,584,000 | 3,661,824 |
| destination | 11,448,320 | 11,464,704 | 11,534,336 | 4,251,648 | 4,165,632 | 4,345,856 |

Both roles observed no more than four threads. These are observed per-process peaks from
the Windows sampler, not an attribution of all bytes to credit state.

## Thousands-channel model (estimate)

The following is a static logical-storage estimate, not a heap measurement.
It adds the observed 136-byte channel value and the 16-byte `HashMap` channel
key: 152 bytes per active channel. It excludes allocator metadata, hash-table
control bytes, spare capacity, and enclosing session structures.

| Active channels | Logical key + value bytes |
|---:|---:|
| 1,000 | 152,000 |
| 4,000 | 608,000 |
| 10,000 | 1,520,000 |

No estimate substitutes for a mandatory gate. The resource gate is supported
by exact epoch/assigned/pending/replay bounds, the 4,000-channel regression,
and the observed five-minute live soak.
