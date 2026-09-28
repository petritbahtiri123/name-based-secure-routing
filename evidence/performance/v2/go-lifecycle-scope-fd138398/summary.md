# Go lifecycle worker scope: Windows release evidence

Source: `fd138398549a579b50dd0693fc278d3998b0b3e0`.

The independent Go benchmark peer previously waited unconditionally at its
concurrent-start barrier. A post-dial error before release could return without
joining those workers or closing the peer. Focused regression tests first failed
because the required lifecycle scope did not exist. The minimal scope now
cancels waiting workers, closes the peer once to unblock I/O, and joins every
owned worker on every post-dial return. Successful destination-completion and
controller-ACK ordering is preserved. No production Rust transport, security
check, wire format or timeout changed.

MEASURED: 18/18 release cells passed: three repeats each of 16/32/64 streams,
16/32 channels, and fifty same-process cycles. All 1680 round trips completed,
including 150 cycles and 1200 cycle round trips. All reported source benchmark
workers were joined (live count zero, exactly one peer-close call per cycle),
all eight instrumented destination ownership counters were zero, and owned
processes exited. The first-three memory CV rule required no extra repeats.
The preceding successful-workload cohort also passed 18/18; this change fixes
the proven early-return path, not a measured successful-path performance limit.

Focused scope/completion tests, `go test -race ./... -count=1`, `go vet ./...`,
gofmt and diff checks passed in `interop/nbsr-go-peer`. One independent focused
review found no Important/Critical correctness or security findings. The RED
result is recorded as a tool-output summary, not a reconstructed compiler log.

DIAGNOSTIC: retained cooldown source private bytes increase roughly 4.5–4.9 MiB
over each fifty-cycle run. Runtime samples range from two to fourteen goroutines;
their final sample precedes the final operations (392 of 400 requests), so it
does not prove fourteen orphan goroutines. The source has no final live cooldown
sample after process exit. These observations do not identify a leak, allocator
retention cause, isolated bytes/resource, observer neutrality or full QUIC
internal ownership. Only the explicit benchmark worker scope is closed here.

`analysis.json` compares all three cycle repeats before and after without
discarding unfavorable data. `raw-evidence.json` binds retained raw roots and
their checksum indexes. Source archives, binaries, commands and each attempt
remain in those raw roots; they must be transferred with this report for an
independent reproduction. This is scoped lifecycle closure, not full B3 or B5
acceptance.
