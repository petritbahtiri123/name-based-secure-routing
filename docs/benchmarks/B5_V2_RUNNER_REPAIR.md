# B5 runner reliability repairs

The current P2A v2 result schema and bounded outstanding-operation workload are
supported. The final analyzer rejects throughput decay over 5% or p99 drift
over 20%; the matching live abort checks now use disjoint first/last thirds after at least
three steady-state progress windows. Accepted ceiling-consumption gates remain pending.

Focused synthetic child processes exposed three runner defects in literal RED:

- Writing 1 MiB to unread stderr blocked the child until its existing timeout.
- A rejected progress line left the child running until the workload timeout.
- An exception in the client-start callback left its owned child alive.

The helper now sends stderr to a file, retains a bounded error tail for the
exception, observes reader failures while waiting under the original deadline,
and encloses setup in owned-process cleanup. An explicit stderr path preserves
the complete diagnostic stream; ordinary callers use disposable temporary disk
storage. No production transport or workload timeout changed.

A fourth RED showed that a failed soak lost already received progress, resource
samples and reproduction commands. B5 now retains commands before process
launch, file-backed source/destination logs, partial parsed records, failure
classification and a raw-cell checksum manifest on exit. Failed/aborted runs
remain INCOMPLETE and cannot become stable-soak evidence.

Validation: 21 focused Python tests passed across `test_measured_client_failure`,
`test_long_run_streaming`, `test_b5_current_runner` and `test_sustained_capacity`;
Ruff passed on the changed Python files. These are harness regression results,
not long-duration performance evidence. Current near-ceiling soak execution is
still pending a defensible current strict-stable load and live abort gates.

Live guard regression: immediate reported errors/timeouts and throughput decay
over 5% or p99 drift over 20% stop the owned source through the existing reader
failure path. The offending window is appended before checking, and partial
evidence remains INCOMPLETE. Literal RED tests showed continuation after failure;
21 focused B5 tests then passed, with Ruff and one scoped review.

The first live comparison can contain one sample per third; this is an early
safety gate, not long-run stability qualification. Source progress begins after
the measurement barrier and excludes warmup. Missing latency samples do not
establish PASS. Thermal/power and measured-safe-boundary live telemetry remain
unimplemented; no new thresholds for those signals are inferred here.

The sampler now records `monotonic_timestamp_ns` immediately after each role's
process read, alongside the unchanged sampler-relative `timestamp_ns` field.
The new field defaults to null for older dataclass callers; old evidence is not
rewritten or assigned a fabricated absolute clock. B5 no longer adds a caller
start time to sampler-relative time, which used different origins.

B5 evaluates live private-memory growth from the progress reader, after raw
resources and the triggering progress window have been appended. The first
progress arrival is the conservative steady cutoff; samples before it and after
the latest progress arrival are excluded. Both source and destination need at
least four eligible samples before the live guard evaluates either. Live and
offline checks share the existing predicate: positive slope, R-squared at least
0.8, and first-to-last growth greater than max(1 byte, 2% of final private bytes).
A failure enters the existing reader abort/owned-child cleanup path and retains
partial resources, progress, failure metadata and checksums.

Final/cooldown records do not trigger a growth check. Offline phase tagging uses
the same first/last progress-receipt bounds with the actual absolute sample
clock. Samples before the first arrival are labelled `pre_first_progress`,
because they include both warmup and the first measured prefix. These are
conservative receipt-based observation bounds, not exact child
phase timestamps; progress transport delay remains possible. The estimated
`measurement_relative_ns` is retained for diagnostics and does not choose phases.
This excludes the pre-first-progress measurement prefix as well as warmup from
the growth decision. Four early points may rise before an eventual plateau; an
abort is an early safety/resource-growth diagnostic, not proof of unbounded
growth or an allocator leak. No timeout or offered-load reduction was added.

Literal RED regressions covered the missing absolute clock, warmup/post-progress
exclusion, continued execution after growth, and skewed relative-origin phase
tagging. The focused resource/B5 suite passed 37 tests after correction.

## Optional host-power observations

`--host-power` is off by default. When explicitly enabled, each received progress
window triggers one `GetSystemPowerStatus` and one read-only
`CallNtPowerInformation(ProcessorInformation)` call on the existing reader path.
No new thread, service, threshold, load change or timeout is introduced. Raw
records are retained separately in `power.ndjson`, including on abort, and are
covered by the run's checksums. Final/cooldown messages do not trigger sampling.

Each record has a monotonic timestamp, per-API call cost, numeric return/error
status and raw fields. DLL bindings are cached; per-API cost excludes initial
binding setup. Exceptions are never rendered. API failure or unsupported binding
produces explicit `UNAVAILABLE` and null fields; it does not establish successful
power observation or a thermal-health result. The run analysis separately records
whether power sampling was requested and available, without changing existing
capacity gates.

These are [OS power-state fields](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-getsystempowerstatus)
and [OS-reported processor MHz/limits](https://learn.microsoft.com/en-us/windows/win32/power/processor-power-information-str),
not effective CPU frequency, package temperature, throttling attribution or
watts. Processor enumeration follows `GetSystemInfo`'s current group (at most 64);
no all-groups claim is made. Raw unknown sentinel values remain unchanged.
An observer comparison remains required before interpreting a soak with this
option enabled; the single nonadmin availability probe does not prove negligible
sustained observer cost.
