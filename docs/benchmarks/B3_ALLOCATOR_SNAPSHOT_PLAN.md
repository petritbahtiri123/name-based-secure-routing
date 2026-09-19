# B3 allocator attribution experiment

The remaining question is allocator retention versus growing allocation state,
not whether nonzero RSS alone constitutes a leak. Add an opt-in, benchmark-only
Linux/glibc `malloc_info(0, FILE*)` snapshot at source lifecycle entry and after
each existing completed cycle. It reports all arenas; no malloc tuning, trimming,
keepalive, timeout or security change is permitted. Unsupported hosts reject the
requested observer rather than silently omit it. Default behavior stays off.

Keep raw XML with bounded version-aware parsing. Report arena system bytes,
reported free chunks and mmap bytes separately from OS private-resident samples.
System minus reported free bytes is a derived remainder, not exact live Rust
allocation size: allocator metadata, caches and sampling uncertainty remain.
Source-only observations cannot establish destination allocator cleanup.

Use literal RED/GREEN tests, a focused correctness review, release builds and
matched observer-off/on same-process cycle controls before longer diagnostics.
Retain every failed/unfavorable result. Compare existing latency/resource gates;
reject causal performance attribution if observer thresholds are exceeded.
No production optimization follows unless attribution justifies it.

Reference: [Linux malloc_info interface documentation](https://man7.org/linux/man-pages/man3/malloc_info.3.html).
This experiment is not a change to the frozen NBSR protocol or allocator policy.
