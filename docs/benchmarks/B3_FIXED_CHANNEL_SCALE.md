# B3 fixed-channel stream scale

The default eight-channel series remains unchanged. An explicit
`--fixed-channels 32` selects a separate stream-residency series with 32 fixed
channels and 1..64 streams/channel, permitting 32..2048 streams. Existing fixture
authority supports at most 32 services, and production transport already advertises
2049 bidirectional streams including control. None of those limits is changed.

Only the streams axis accepts a non-default fixed-channel override. Counts must
be divisible by the fixed channel count. Wide cells have distinct names such as
`streams-c32-2048-r1`; the analyzer rejects mixed resource scopes instead of
pooling channel overhead into a misleading stream-memory slope.

Literal RED: ten tests failed for the missing fixed-channel API or failure to
reject mixed scopes, while the default-shape regression already passed.
GREEN: twenty focused B3 specification/analysis tests pass, scoped Ruff and diff
checks pass. Raw test logs are retained at
`C:/NBSR-build/b3-fixed-channels-red.log` and
`C:/NBSR-build/b3-fixed-channels-green.log`.

This is an executable workload definition, not a successful 2048-stream result.
A read-only bounded review identified a possible destination audit-consumer gap
in the later materialization phase above 1024 streams; the next live diagnostic
must preserve that failure before any repair. Mandatory audit checks, queue cap,
protocol timeouts, payload, ACCEPT and response/send-ACK semantics stay unchanged.

After building the exact release source, use a fresh output directory:

```powershell
python scripts/run_b3_v2.py --output C:/NBSR-build/b3-wide-diagnostic --target C:/NBSR-build/b4b-task4k --axis streams --fixed-channels 32 --counts 2048 --repeats 1 --materialized-streams
```

One repeat is DIAGNOSTIC. A successful scale claim still requires the configured
three/five-repeat gates, both-endpoint materialization and complete cleanup.
