# P2D security matrix

| Property | Evidence | Result |
|---|---|---|
| Explicit profile; no silent fallback or Core numeric change | `legacy_fallback_requires_policy_permission_and_preserves_legacy_flow`: omitted/explicit required-V1 downgrade fails while explicitly allowed Legacy keeps the unchanged Core path | PASS |
| V1 cannot bypass credit through legacy stream entrypoints | `v1_rejects_legacy_stream_paths_without_mutation_then_accepts_credited_retry`; live `live_v1_rejects_legacy_stream_open_then_credited_retry_succeeds`; credited-only permit validation | PASS |
| Exact session/channel/route/grant/generation/revocation binding | `consume_rejects_invalid_duplicate_and_wrong_authority_without_mutation`; live wrong-channel integration | PASS |
| No application payload before same-stream ACCEPT | `credited_stream_waits_for_same_stream_accept_then_echoes_without_stream_open` | PASS |
| Bounded, closed preface parsing | exact vector suite; bounded-reader malformed/oversized/truncated tests; malformed live integration | PASS |
| Slot and stream replay remain independent and fail closed | exact 64-slot exhaustion, duplicate/race tests, live replay checks | PASS |
| P1F replay bound preserved | authoritative live paths use exact `ReplayHistoryLimit(10000)`; all nested endpoints in 24 cells / 1,257 shards / 2,514 endpoints audited, with any violation a FAIL | PASS |
| Revocation dominates unused credit | `revocation_before_destination_commit_rejects_and_retains_source_replay` | PASS |
| Failure isolation and sibling progress | wrong-channel and timed-out-admission live integrations | PASS |
| Exactly one ordered authenticated control stream | live integration reuses the original Quinn control stream for refill and proves every second open/accept fails closed | PASS |
| Refill frame is fixed, closed, and type-checked | 30-byte body / 31-byte framed request and grant vectors; malformed/version/kind/epoch decoding rejects | PASS |
| Refill does not block at watermark or create a RouteGrant | state test keeps the final 16 current credits usable; live benchmark reuses the existing channel authority | PASS |
| Draining refill request is atomic | a request while draining returns `DrainingEpoch` before pending mutation and a later legal retry succeeds | PASS |
| Epoch and pending state are bounded | current plus one draining epoch, one pending request; third epoch and wrap reject | PASS |
| Draining retirement waits for terminal streams | compact per-epoch assigned counters; reordered old/new terminal cleanup; duplicate release decrements exactly once | PASS |
| Grant revalidates live headroom without reservation | exact full-channel, P1F exhaustion, retry, and quota audit tests; no stream/replay/RouteGrant reservation | PASS |
| Capacity/audit failures do not consume credit | transactional prepare/commit tests and existing channel admission gates | PASS |
| Live correctness and unexpected errors | smoke, seven-point sweep, six paired cells, continuity, and soak all report correct 1 KiB echo and zero errors | PASS |

Fresh focused verification and the clean pre-output whole-Git-tree binding are
recorded in the package final report and Task 4 report. Attempt 7's runtime
audit finalized PASS after every cell boundary retained the exact commit,
HEAD/index tree, and output-root-only status. The benchmark is loopback-only
evidence; it is not a multi-host, adversarial-network, or production-capacity
claim.
