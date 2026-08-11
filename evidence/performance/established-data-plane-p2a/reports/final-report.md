# P2A True Established Data-Plane Baseline

## Executive summary

Classification: **ACCEPTED_WITH_UNSTABLE_CELLS**. All 18 matched cells completed, all 60 measured repeats passed payload/sequence validation, and every timed TS/SC/Application Stream/replay delta was zero. Six selective repeats were used. Direct and NBSR 64-stream/16-KiB cells remained above 5% CV after five repeats and are lower-confidence observations. No optimization was implemented.

One operation is one deterministic framed request plus its matching framed response over the same pre-established bidirectional stream. Every stream uses one outstanding request at a time.

## Established Rust NBSR capacity

| Payload bytes | Streams | Direct ops/s | NBSR ops/s | NBSR/Direct | NBSR aggregate Gbps | NBSR p50/p95/p99 us | NBSR CPU ns/op | NBSR CV | Stable |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|:---:|
| 1 | 1 | 13271.69 | 12260.18 | 0.9238 | 0.000196 | 87.7/104.8/121.7 | 111941.9 | 0.214% | yes |
| 1 | 8 | 75485.32 | 74299.56 | 0.9843 | 0.001189 | 110.3/124.5/149.2 | 17857.8 | 0.210% | yes |
| 1 | 64 | 205598.09 | 198511.45 | 0.9655 | 0.003176 | 321.7/349.7/412.1 | 6120.0 | 0.735% | yes |
| 1024 | 1 | 10505.01 | 10568.12 | 1.0060 | 0.173148 | 98.4/114.0/132.8 | 125557.6 | 1.461% | yes |
| 1024 | 8 | 31676.42 | 31336.75 | 0.9893 | 0.513421 | 251.1/284.2/321.5 | 39369.9 | 0.123% | yes |
| 1024 | 64 | 56117.20 | 55372.32 | 0.9867 | 0.907220 | 1139.2/1441.6/1574.3 | 27281.9 | 0.524% | yes |
| 16384 | 1 | 2455.43 | 2439.84 | 0.9937 | 0.639591 | 405.5/432.6/486.4 | 539814.6 | 1.008% | yes |
| 16384 | 8 | 3928.12 | 3895.04 | 0.9916 | 1.021062 | 1999.1/2946.6/3364.1 | 368491.5 | 4.878% | yes |
| 16384 | 64 | 3825.33 | 3823.74 | 0.9996 | 1.002370 | 16594.4/19051.9/21819.1 | 371766.3 | 21.179% | NO |

The highest stable NBSR operation rate is the 64-stream, 1-byte cell. The highest stable NBSR aggregate application goodput is the 8-stream, 16-KiB cell. The 64-stream, 16-KiB observation is not used as a stable headline.

## Lifecycle isolation and correctness

Across every repeat: Transport Session creation delta = 0, Service Channel creation delta = 0, Application Stream creation delta = 0, replay-entry delta = 0, and errors/timeouts/missing/duplicates/corrupt/wrong-request responses = 0. Setup and warm-up precede the measurement barrier. Process CPU and memory use only the final measured-duration resource-sample tail. Allocation telemetry was unavailable and no allocator profiler was added.

## Scaling and indications

One-byte throughput scales strongly from 1 to 8 to 64 streams, which is consistent with a single-stream latency bound. At 1 KiB scaling remains positive but sublinear. At 16 KiB, 1 to 8 streams improves throughput, while 64 streams is unstable and does not provide a reliable further-scaling claim. High-concurrency large-payload behavior could be scheduler/CPU or copy/serialization related, but P2A has no profile evidence and assigns no root cause.

## Old benchmark comparison

The accepted 1,687.5 req/s Rust-to-Rust result measured a new `STREAM_OPEN`, admission/acceptance, QUIC Application Stream opening, one exchange, and release per operation. P2A creates and admits the fixed stream set before warm-up and measures repeated framed exchanges only. Therefore 1,687.5 req/s is a lifecycle/establishment capacity and is not established-data-plane throughput.

## Integrity and non-claims

The benchmark feature is disabled by default and adds no production protocol behavior. Direct and NBSR share the same payload bytes, frame codec, validation, warm-up, measured duration, persistent stream counts, and one-outstanding model. P1F replay semantics and prior evidence were not modified. P2A is Windows loopback evidence on this machine, not Internet, regional, production-readiness, or root-cause evidence.

## Recommended next task

Exactly one next task: **P2B profile-only investigation of the unstable 64-stream/16-KiB established-data-plane cell, using the frozen P2A harness and no optimization.**
