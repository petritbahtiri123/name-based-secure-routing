# B2-v2 Plateau Profiling

Classification: **Evidence PARTIAL / System UNRESOLVED**

The plateau reproduced without allocated-core saturation, but this run cannot defensibly name its owner. The established benchmark is one-outstanding-per-stream, the NBSR destination rejects stream counts outside 1/8/64, and WPR CPU stack capture was denied with no installed exporter. These are measured diagnostic limitations, not proof of the plateau cause.

## Representative cells

| Path | Payload | Streams | Mask | Gbit/s | Effective cores | p99 ms | CV |
|---|---:|---:|---:|---:|---:|---:|---:|
| direct | 1024 | 64 | 0x1 | 0.511 | 0.865 | 4.309 | 0.004 |
| direct | 1024 | 64 | 0x5 | 0.775 | 1.270 | 3.224 | 0.064 |
| direct | 1024 | 64 | 0x55 | 0.934 | 1.363 | 1.595 | 0.016 |
| direct | 16384 | 8 | 0x1 | 0.696 | 0.876 | 5.237 | 0.005 |
| direct | 16384 | 8 | 0x5 | 1.038 | 1.294 | 3.623 | 0.023 |
| direct | 16384 | 8 | 0x55 | 1.026 | 1.334 | 3.527 | 0.024 |
| nbsr | 1024 | 64 | 0x1 | 0.575 | 0.884 | 3.802 | 0.007 |
| nbsr | 1024 | 64 | 0x5 | 0.933 | 1.349 | 1.915 | 0.025 |
| nbsr | 1024 | 64 | 0x55 | 0.918 | 1.332 | 1.685 | 0.020 |
| nbsr | 16384 | 8 | 0x1 | 0.680 | 0.879 | 5.174 | 0.017 |
| nbsr | 16384 | 8 | 0x5 | 1.040 | 1.272 | 3.320 | 0.001 |
| nbsr | 16384 | 8 | 0x55 | 1.016 | 1.314 | 3.273 | 0.015 |

## Recommendation

Do not optimize production code. First enable a readable stack/wait profiler and add a separately approved harness-only scalable outstanding/stream diagnostic.
