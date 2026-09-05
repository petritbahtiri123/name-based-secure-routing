# B1 V2 packet-accounting method

The opt-in capture runner uses matched Direct/NBSR fixed-operation workloads and
captures only the relay's server-facing UDP leg on NPF_Loopback. Capture timing
is DIAGNOSTIC and cannot establish performance capacity. Five alternating pairs
per payload are the default; a one-repeat smoke is regression evidence only.

Before starting any workload, two separately reserved loopback sockets send a
random 32-byte readiness token. A bounded pcapng-prefix reader must find a
complete captured probe before the runner proceeds. The final closed capture is
independently decoded by TShark; exact tuple, token and frame inventory identify
every probe, which is excluded from workload totals. No probe targets QUIC.

The capture must have one NULL/Loopback interface, complete packets, one workload
flow, consistent IPv4/UDP lengths, no fragmentation and zero reported drops.
Full numbered frame inventory, probe frames, workload frames and dumpcap counts
must reconcile. Missing drop evidence is not treated as zero loss.

Reported IP/UDP lengths and packet counts are measured from the capture.
UDP payload bytes are derived from measured UDP length minus its header.
NULL/Loopback frame bytes are not physical Ethernet bytes; physical L2 cost is
NOT_PROVEN. Generic secure-transport framing is not labeled an NBSR tax.

The packet phase is the **whole capture**: setup, fixed useful operations,
matched untimed frame-validation exchanges and teardown. The useful-byte
denominator excludes validation exchanges, so expansion ratios include those
fixed fixture costs. Established-only packet accounting remains NOT_PROVEN.
The primary comparison is the incremental paired NBSR-minus-Direct delta under
this identical scope, with dispersion and unfavorable pairs preserved.

Validation: 27 focused parser/readiness/hook tests passed. The verified smoke
`C:/NBSR-build/b1-v2-verified-readiness-smoke-prefix` passed four captures:
workload/probe counts 64/6, 77/5, 449/6 and 464/6; all capture drops zero.
Earlier readiness failures remain retained. Full repeated accounting and its
derived delta are a separate pending evidence stage.
