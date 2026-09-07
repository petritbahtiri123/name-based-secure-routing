# B5 latency-sample residency artifact

The 8779e69c Linux strict loader accepted the new NBSR depth-one finite reference
and derived 70% load:6676826000000/85751993 operations/s. The first declared
120-second ownership-off control aborted at its first 10-second progress window
on source private-resident growth. It remains FAIL; ownership-on was not run and
no observer qualification is established. Other drift/error/cleanup rules were
not suppressed. The traceback and failed prefix are retained.

Twenty steady source memory samples grew114688 bytes in9.557seconds; fitted
slope10530.30 bytes/s,R-squared0.97489. The first window retained12067 u64 latency
samples at stride64:96536 bytes, with9653.38 sample-write bytes/s. This strongly
matches gradual first-write residency, but does not attribute every byte.

Source inspection shows BoundedCollector::new and AsyncRun::new reserve empty
Vec capacity without touching sample storage. The configured capacity is24347
u64 elements. A release Rust probe reproduces those exact capacity/sample counts
in three independent process pairs. Reserve-only grows from1 to24 resident pages;
explicit pre-touch before filling stays48 to48, every pair. mincore observes the
allocated sample region directly. This proves the harness's lazy sample-storage
residency mechanism independently of NBSR/QUIC; it is not a production leak proof.

Smallest proposed correction: initialize both reserved sample buffers before the
measurement barrier, then clear logical length and retain the same capacities,
stride, sampling, guards and reuse behavior. This makes fixed harness memory
resident earlier and may increase initial RSS; it is NOT a memory-reduction
claim. No timeout, guard or workload is relaxed. Actual rerun is required to
determine whether residual non-sample growth remains.

Raw roots/checksums are in raw-evidence.json. The probe uses Rust1.97.1,edition2024,
optimized rustc output, and only Linux mapping-residency metadata. No Windows
Administrator action, production code change or memory-content capture was used.
