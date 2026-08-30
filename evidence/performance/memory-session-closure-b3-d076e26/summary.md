# B3 Memory / Session Lifecycle

Authoritative scope: Windows 11 loopback, release Rust destination, base SHA `d076e26d7c95f8f559bc4ee02e677eb3291ea927`. Counts 1/2/4/8 were sampled for live connections, channels, and application streams. All eight destination ownership counters returned to zero after every cell.

## Rust to Rust

Evidence: **PARTIAL**. Lifecycle: **CLEAN**.

| Resource | Counts | Idle private bytes | Active private bytes | Incremental private bytes | Fitted slope |
| --- | --- | --- | --- | --- | --- |
| Connections | 1/2/4/8 | 1,429,504–1,449,984 | 1,810,432–3,436,544 | 380,928–1,998,848 | 230,961 bytes/connection |
| Channels | 1/2/4/8 | 1,431,552–1,441,792 | 1,789,952–1,855,488 | 358,400–421,888 | below measurement resolution |
| Streams | 1/2/4/8 | 1,433,600–1,445,888 | 1,822,720–1,847,296 | 385,024–411,648 | below measurement resolution |

Five process-isolated 8-stream cycles had a fitted cooldown private-byte slope of -25,395 bytes/cycle. This is not evidence of memory savings and not a same-process allocator staircase test.

## Go to Rust

Evidence: **PARTIAL**. Lifecycle: **CLEAN**.

| Resource | Counts | Idle private bytes | Active private bytes | Incremental private bytes | Fitted slope |
| --- | --- | --- | --- | --- | --- |
| Connections | 1/2/4/8 | 1,421,312–1,445,888 | 1,847,296–3,403,776 | 405,504–1,957,888 | 222,466 bytes/connection |
| Channels | 1/2/4/8 | 1,425,408–1,445,888 | 1,814,528–1,847,296 | 389,120–405,504 | below measurement resolution |
| Streams | 1/2/4/8 | 1,429,504–1,441,792 | 1,822,720–1,859,584 | 389,120–430,080 | below measurement resolution |

Five process-isolated 8-stream cycles had a fitted cooldown private-byte slope of +12,698 bytes/cycle, below the 64 KiB/cycle growth threshold. Go runtime samples observed 2–14 goroutines. This is not a same-process goroutine or allocator staircase test.

## Limitations

The lifecycle server serializes admitted sessions. A same-process multi-session staircase therefore remains unproven; process-isolated cycles reset allocator state and justify PARTIAL rather than PASS. The existing 10-second lifecycle acknowledgement bound also limited reliable held-resource cells to eight active channels/streams. No timeout was increased and no transport, authorization, trust, replay, or wire behavior was changed.
