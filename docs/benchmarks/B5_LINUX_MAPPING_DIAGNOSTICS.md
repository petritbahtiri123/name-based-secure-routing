# Linux B5 residual memory diagnostics

Source/build:857b4080; unchanged release binaries and fixed offered rate from
`B5_SAMPLE_PREPARATION.md`. These are failed or observer-unqualified diagnostics,
not accepted soak capacity. No production optimization follows from them.

Three additional120second attempts sampled owned-process mappings every10seconds.
Repeat1 failed destination-private growth, repeat2 completed with97.999% of
offered work and11-counter/process cleanup, repeat3 failed destination-private
growth. Every result is retained. The mapping observer has no accepted matched
three-valid-repeat qualification. Snapshot duration below1ms is not sufficient
to establish negligible observer overhead.

In the first two attempts, destination growth occurred inside existing anonymous
mappings/heap; file-backed mappings did not account for their sampled growth.
The large anonymous mapping retained the same3,018,752byte virtual extent.
This distinguishes increased residency within a reservation from an observed
increase in that reservation; it does not prove all ownership is bounded.

A separate glibc calloc interposer recorded only large allocation pointers and
stacks, without changing requested size, returned contents or allocator.
Its zero-initialization/overflow/ENOMEM passthrough probe passed. Address-to-mapping
correlation found a3,014,656byte allocation inside the destination mapping in all
three instrumented attempts. Binary symbols resolve its allocation stack to
`quinn::endpoint::Endpoint::new_with_abstract_socket`, then `Endpoint::new`, then
`TransportListener::bind`. The locked Quinn0.11.11 receive buffer formula and
quinn-udp0.5.15 Linux constants yield1472 *64 *32 =3,014,656bytes. This is a
DIAGNOSTIC allocation identification, not a qualified causal performance result.
Source mappings containing the corresponding buffer also contain adjacent memory;
do not attribute every changed page exclusively to that buffer.

All three allocator-instrumented attempts failed: p99 drift, destination-private
growth, p99 drift. Reject this cohort for performance attribution and capacity
claims. The size/pointer observations are retained as diagnostic leads only.
No change to GRO, UDP payload limits, protocol, security, timeouts or growth
assertions was made. Prefaulting a transport reservation would increase initial
resident memory; it must not be presented as a memory-saving optimization.

Remaining: qualified sustained testing, reliable separation of live allocation
growth from residency/allocator retention, and a valid observer comparison.
Do not call this a proven production leak, a hardware ceiling, or a passed soak.

Canonical evidence: `evidence/performance/v2/b5-mapping-diagnostics-857b4080`.
It contains every raw-root index, all six records, correlation/analysis scripts,
profiler source and the Windows B5 test log (50PASS,1existing ignored).
The original failed uninstrumented prefix remains in
`evidence/performance/v2/b5-pretouch-857b4080`.
