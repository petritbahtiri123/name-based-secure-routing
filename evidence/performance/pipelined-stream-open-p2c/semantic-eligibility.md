# P2C semantic eligibility trace

1. `ControlEnvelope.request_id` is the request correlation key and is session-unique.
2. `STREAM_ACCEPT`/`STREAM_REJECT` echo that request ID and the established session ID.
3. A request ID is nonzero, unique within the Transport Session, and retained by `ControlSession.request_ids` after a successful commit.
4. Source and destination `monotonic_sequence` values are separate strictly increasing sequences committed in control-wire order.
5. Source bidirectional QUIC IDs are 0, 4, 8, ...; stream 0 is the sole control stream and application streams start at 4.
6. QUIC allocates a real bidirectional stream ID from the connection when `open_bi` succeeds.
7. Several future IDs can be held safely only by retaining the actual Quinn stream handles; arithmetic prediction alone is insufficient.
8. A retained handle consumes its actual ID, so another opener receives a later ID. The candidate used actual handles and rejected permit/ID mismatch.
9. Core v0.2 framing allows multiple sequential control frames and requires only that no application bytes be sent before the matching accept; it does not require one outstanding request.
10. The reliable control stream emits responses in processing order in the existing destination loop.
11. Responses are independently correlatable by request/session plus echoed stream/channel/route bindings.
12. Destination admission commits remain in control-message order because authorization is sequential.
13. `ChannelStreams::prepare_open` checks the 64-stream per-channel limit before `commit_open`; sequential destination commits prevent oversubscription.
14. P1F checks committed `used_stream_ids` against the hard replay-history limit during every prepare; sequential prepare/commit prevents pending candidates from exceeding the cap.
15. Authorization audit is recorded before stream-state and source-control commit, retaining deterministic audit order and fail-closed audit behavior.
16. A rejected candidate must reset/drop only its held silent stream and remove only its exact pending entry; neighboring bindings remain distinct.
17. Cancellation or timeout drops the held handle and bounded entry. The QUIC ordinal remains consumed, while no destination replay entry is committed for an admission that failed before commit.
18. Channel revoke removes applicable pending entries; connection/session close clears all. Existing session/channel revocation remains authoritative and no reserved stream can become an application stream without the normal exact permit.

## Eligibility conclusion

The frozen protocol can represent bounded pipelining without a wire change if actual silent Quinn streams are reserved and exact existing correlations are enforced. The candidate was therefore eligible to implement. It was later reverted for failing the mandatory p99 performance gate, not for a protocol-semantic blocker.
