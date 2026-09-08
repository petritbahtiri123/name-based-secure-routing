# Linux active resource scale and receive-buffer sensitivity

MEASURED: current release source0124f8ad passes five repetitions of2048 active,
materialized authenticated connection/session/channel/stream bundles with two
allocated guest CPUs, and five with four. Final ownership validation passes.
Source/destination active-private-resident medians are765952000/638349312bytes
(two CPUs) and769716224/638582784bytes (four). Per-role CV is0.36-1.01%.
These are process costs including QUIC/runtime/allocator/fixtures, not pure
NBSR object sizes. The summed role medians are1404301312 and1408299008bytes.
Guest topology is not verified physical-host topology; no server ceiling claim.

DIAGNOSTIC: all six counterbalanced one-CPU2048 attempts fail, three with the
Linux default212992-byte actual receive buffer and three requesting1MiB,
clamped to425984bytes. Source handshake-timeout counts are317/227/75 versus
63/80/958, respectively; failures and task panics are retained. This dispersed
comparison does not justify a Linux production buffer optimization.

The first four-CPU4096 attempt fails with891 source handshake timeouts and one
client_task_failed (ControlStreamFailed panic retained). Its owned destination
socket reports76649 cumulative receive drops; retained source sockets report0.
No replacement repeats were used to conceal the failed progression. Failure-only
snapshots identify a socket, not drop timing or the sole cause of all timeouts.

Earlier132a3b82 snapshots and diagnostic RED/GREEN validation are included in
raw indexes. No security/wire/production-default change was made in this stage.
No sustained-soak, allocator-retention cause, or global hardware ceiling is proven.
