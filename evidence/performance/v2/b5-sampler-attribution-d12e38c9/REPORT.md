# B5 sampler attribution attempt

Source `d12e38c95a0d5f8d02a78eb7a797af11969f81a2`; Windows loopback.
**INVALID_PARTIAL_DIAGNOSTIC**, not an observer comparison or qualified soak.

The fixed historical load and five-attempt maximum were declared before runs.
Attempt 1 completed diagnostically at 0.570874 Gbit/s with achieved/offered
0.934056 (below the qualified 95% gate). Attempt 2 aborted on live goodput drift:
three steady windows fell from 72,497,228 to 59,812,327 bytes/s; p99 rose from
2.246 to 8.558 ms. No third attempt or replacement was run.

The new failure traceback is retained and identifies the live goodput guard.
The earlier sampler lookup failure was NOT_REPRODUCED before this different
abort. Its cause remains UNRESOLVED; no production optimization follows.
Static investigation found that the single-group NBSR benchmark destination
returns after cleanup without consuming the supplied completion-ACK path.
This is a candidate lifecycle mismatch with B5 sampling, not a proven cause
of the earlier capture. Do not claim a fix or neutral observer.

All 42 indexed raw artifacts were freshly verified in
`C:/NBSR-build/b5-sampler-attribution-d12e38c9`.
Raw index SHA-256:
`3ea5503a1a019e12bf36efc00f9b86d8bd51bb0289fef13a99422eec04eb7144`.
The complete raw prefix, traceback, commands, resource and ownership streams,
binaries, source provenance and nested indexes remain there.
