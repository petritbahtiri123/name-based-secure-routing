# P2D security matrix

| Property | Evidence | Result |
|---|---|---|
| Explicit profile; no silent fallback or Core numeric change | Normative `design/stream-credit-extension.md`; existing legacy path remains separately selected | PASS |
| Exact session/channel/route/grant/generation/revocation binding | `consume_rejects_invalid_duplicate_and_wrong_authority_without_mutation`; live wrong-channel integration | PASS |
| No application payload before same-stream ACCEPT | `credited_stream_waits_for_same_stream_accept_then_echoes_without_stream_open` | PASS |
| Bounded, closed preface parsing | exact vector suite; bounded-reader malformed/oversized/truncated tests; malformed live integration | PASS |
| Slot and stream replay remain independent and fail closed | exact 64-slot exhaustion, duplicate/race tests, live replay checks | PASS |
| P1F replay bound preserved | authoritative live paths use exact `ReplayHistoryLimit(10000)`; 24 cells and 2,540 shard endpoints audited | PASS |
| Revocation dominates unused credit | `revocation_before_destination_commit_rejects_and_retains_source_replay` | PASS |
| Failure isolation and sibling progress | wrong-channel and timed-out-admission live integrations | PASS |
| Ordered refill uses an authenticated control stream | `ordered_live_refill_follows_exhaustion_and_synchronizes_bounded_epochs` uses actual Quinn endpoints | PASS |
| Refill frame is fixed, closed, and type-checked | 30-byte body / 31-byte framed request and grant vectors; malformed/version/kind/epoch decoding rejects | PASS |
| Refill does not block at watermark or create a RouteGrant | state test keeps the final 16 current credits usable; live benchmark reuses the existing channel authority | PASS |
| Epoch and pending state are bounded | current plus one draining epoch, one pending request; third epoch and wrap reject | PASS |
| Capacity/audit failures do not consume credit | transactional prepare/commit tests and existing channel admission gates | PASS |
| Live correctness and unexpected errors | smoke, seven-point sweep, six paired cells, continuity, and soak all report correct 1 KiB echo and zero errors | PASS |

Fresh focused verification is recorded in the package final report and Task 4
report. The benchmark is loopback-only evidence; it is not a multi-host,
adversarial-network, or production-capacity claim.
