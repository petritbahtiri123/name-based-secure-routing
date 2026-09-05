# B3-v2 harness repair, 2026-09-05

This is an engineering stage, not final memory-scale acceptance. All measurements are Windows loopback release builds. Frozen protocol and production library semantics are unchanged.

## Measured defects and corrections

- Blocking lifecycle marker waits prevented sibling logical clients from progressing on a current-thread runtime. A literal failing runtime test now passes with asynchronous waits and unchanged deadlines.
- Rust scale now uses one source process with two runtime shards instead of one process per client. Retained stdout/stderr files remove unread-pipe backpressure.
- Pre-arming every accept deadline caused late paced clients to exhaust the accept window before arrival. B3 explicitly arms one accept at a time while admitted session tasks remain concurrent. B4 retains its existing accept window. This is a memory-hold workload, not an admission capacity claim.
- Five same-process cycles with 64 streams failed when the echo harness dropped a response before send completion. Both lifecycle echo branches now await the existing `wait_for_send_ack()` API. This preserves ACK semantics; application-processing timings now include that wait and require fresh comparisons.
- Cooldown samples were assigned to the following cycle. They now belong to the cycle just closed. A final out-of-band release gate retains the single source runtime during its last cooldown. Per-cycle diagnostics require all eight owned-resource counters to be zero.

## Retained diagnostic evidence

All roots below are under `C:\NBSR-build`; source snapshots, binaries and checksum indexes are retained by the runner. Dirty-source runs are bound to their retained patch and source copies, not represented as clean-HEAD runs.

| Root | Result |
| --- | --- |
| b3-v2-smoke-387f9f23 | 16 bundles, one process, cleanup zero |
| b3-v2-scale-387f9f23 | Five valid repeats each at 16/32/64/128/256; 512 failed pre-armed acceptance deadlines |
| b3-v2-paced-smoke-387f9f23 | 512 failed with three exhausted accept slots; preserved |
| b3-v2-serial-accept-smoke-387f9f23 | 512 bundles completed, cleanup zero; diagnostic single repeat |
| b3-v2-1024-smoke-387f9f23 | Failed response completion; active markers alone did not prove healthy held connections. Setup exceeded the destination's 10-second idle policy. No memory or hardware ceiling established; deadline unchanged. |
| b3-v2-cycles-red-387f9f23 | Invalid invocation exposed missing diagnostics argument value; repaired |
| b3-v2-cycles-label-red-387f9f23 | Response completion race in repeated 64-stream cycles |
| b3-v2-cycles-ack-smoke-387f9f23 | Five cycles completed after ACK wait; cooldown-label assertion still failed |
| b3-v2-cycles-finalhold-smoke-387f9f23 | Five cycles completed; source per-cycle and final ownership zero; cooldown labels 0 through 4, source retained through final sample |

## Verification and remaining gates

Release Rust B3 helper tests: 4 passed. Python B3/source-plan and session closure tests: 3 passed. Focused Ruff, fmt and release Clippy with warnings denied passed. Release source/server builds passed. Focused review found no Important issue; subsequent cooldown-gate diff was inspected locally.

Required next: clean-SHA repeated resource ladders, 50 same-process cycles, memory slopes with uncertainty, and current forwarding/admission reruns after the ACK timing correction. Bundle cost couples connection, session, channel and stream. Channel cost includes one stream per channel. Windows private bytes/RSS do not identify allocator heap or prove a leak.
