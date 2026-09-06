# Three repeated live ownership controls

DIAGNOSTIC integration only: clean aec0a989, matching binary hashes and verified
shared four-physical-core mask 85 across all three attempts. Both paths use four
groups, 16 KiB, one stream/group, depth one, 2,000 offered operations/s, three-second
warmup, 120-second issue duration, and the predeclared thirty-second progress cadence.
NBSR periodic ownership is enabled; Direct runtime ownership is NOT_MEASURED.

All six runs pass accounting and process cleanup. NBSR's three runs pass sampled
ownership coverage/no sustained growth and all fifteen post-close reports show
eleven zero counters. No errors/timeouts or collector overflow are reported.
Descriptive median goodput: Direct 0.522279 Gbit/s (CV 0.2311%), NBSR 0.522488
(CV 0.1901%). NBSR achieved/offered ranges 99.3446–99.6850%. These fixed-rate light
probes do not establish capacity, zero overhead, or an authoritative long soak.

The source, binaries, shape, placement and rate were checked equal across repeats.
All 168 raw entries were freshly verified. Full original stdout, resource streams,
ownership files and receipt metadata remain at the three external roots in
raw-index.json. Read-only external evidence preparation occurred during diagnostic
execution; no competing build, Docker run or test suite was active during timing.

The earlier one-second-window drift abort remains preserved separately. No threshold,
offered rate, timeout or security rule was weakened to obtain these results.
Near-ceiling sampling off/on qualification, current finite capacity calibration,
and the prescribed long repeated soaks remain outstanding.
