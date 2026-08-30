# B3 Development Failures

Invalid harness-development runs were preserved outside the repository at `C:\NBSR-build\b3-failed-runs-20260830` and excluded from authoritative calculations.

- Rust lifecycle source and destination called endpoint-wide `wait_idle()` while per-session control/session handles or the listener remained live, producing `CloseTimeout`. The benchmark-only lifecycle path now drops owned per-session handles before proceeding; transport implementation and timeout values are unchanged.
- Concurrent connections were accepted in nondeterministic order; the initial runner incorrectly released them by numeric client ordinal. The runner now releases the connection whose active marker is observed.
- Initial channel/stream cardinalities exceeded the unchanged 10-second lifecycle ACK budget while including an observation hold. The authoritative supported range is 1/2/4/8.
- Initial readiness/command evidence exposed local temporary paths. The authoritative rerun keeps readiness and authority files temporary and stores placeholder-based commands.

These failures are harness-development evidence, not valid memory measurements.
