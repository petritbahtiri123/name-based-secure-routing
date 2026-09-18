# Linux B1 packet accounting

This harness measures matched Direct/NBSR IPv4/UDP traffic on Linux `lo`.
It does not measure physical Ethernet, a NIC, WAN capacity or production
throughput. Capture timing is diagnostic only. Both paths retain the same
secure-transport workload and single-flow relay semantics as Windows B1.

Requirements: a clean Linux checkout, release binaries built with
`benchmark-harness`, an exact-SHA build manifest accepted by the Linux B5
drivers, and `dumpcap`, `tshark`, `capinfos` on PATH. The caller must already
have capture permission. The driver does not elevate or change system policy.
Do not inherit `NBSR_*` experiment environment variables.

```sh
python3 -B -m scripts.performance.linux_b1_capture \
  --binaries /absolute/build/binaries \
  --build-manifest /absolute/build/build-manifest.json \
  --output /absolute/evidence/b1-linux --operations 1000
```

The formal cohort runs five counterbalanced pairs for each shape: 1 KiB / 64
streams and 16 KiB / 8 streams, fixed operations, no warmup. A mechanics-only
run uses `--smoke --operations 10` (one pair per payload, one stream). It cannot
support a repeatable-overhead claim. Output must be new and outside the checkout.

Capture covers the server-facing relay leg, including connection setup, useful
operations, matched untimed validation exchanges and teardown. Established-only
packet phase accounting is NOT_PROVEN. The separate relay summary reports its
existing setup/established UDP payload counters; these are different denominators.

The Linux adapter binds the authorized client's PID/start-time, UDP endpoint,
socket inode and file descriptor before accepting its first datagram. Ambiguous
or missing ownership fails closed. This is benchmark isolation, not a new
production authorization mechanism.

Capture must observe an exact random readiness marker before the workload and
a distinct exact terminal marker after it. Both use separate owned loopback
ports. Markers are validated and excluded from workload totals. The terminal
marker prevents stopping dumpcap while the final workload packets are still
buffered. Missing markers, nonzero drops, truncated/fragmented packets,
unexpected interface/encapsulation, multiple flows, or incomplete inventory
invalidate the cell. Existing Windows NULL/Loopback validation remains the
default; Linux explicitly requires untagged Ethernet encapsulation on `lo`.

`packet-summary.json` retains every paired delta, including negative values,
medians, ranges and per-path CV. Generic IP/UDP/QUIC framing is not called an
NBSR tax. Synthetic captured Ethernet lengths are kept separate from measured
IP/UDP lengths; physical Ethernet bytes remain NOT_MEASURED. Five repeats do
not erase residual variability. Invalid attempts are retained without replacement.

The first formal Docker cohort at eb4b0608 was INVALID_PARTIAL: Direct reported
zero drops, but NBSR reported 845 pcap drops (122221 packets captured). Both
attempts are retained. The observer now requests a 64 MiB kernel capture buffer
instead of Dumpcap's 2 MiB default, symmetrically for both paths, without changing
the workload or any timeout. Zero-loss validation still applies to every new cell;
requesting a larger buffer is not evidence that capture loss has been fixed.

The subsequent formal cohort at 6b3d37e8 completed 20/20 captures with zero
reported loss and no workload errors/timeouts. Both exact release builds have
identical binary hashes. This validates the observer correction for the tested
workloads only. See `evidence/performance/v2/b1-linux-packets-6b3d37e8/summary.md`
for paired deltas, CVs, the retained invalid predecessor and raw checksum paths.

Capture is bounded to two GiB per cell and requires two GiB free before the next
cell. Raw pcapng, layer exports, drop statistics, markers, workload commands,
client stdout/stderr, ownership, release hashes and recursive checksums are
retained. Container execution must be labeled Docker/WSL loopback; it is not
native/server-class validation. Capture permission inside a disposable container
does not demonstrate Windows Administrator access.
