# B1 Windows loopback packet accounting

The 20 captures passed readiness, zero-loss, exact-inventory and completed-operation gates. Setup relay UDP-payload deltas were consistently positive in these five matched pairs. Established-window and whole-capture deltas cross zero; neither supports a stable-sign incremental overhead claim.

**Classification: local accounting evidence PASS; phase-aligned IP/L2 accounting NOT_PROVEN.** No timing, capacity, physical Ethernet, WAN or production claim follows.

## Workload and provenance

Source SHA: `e2c75b598b213b4fafbd50aeb93e06edc06b864e`. Each workload used five matched Direct/NBSR pairs, alternating execution order: 1,024-byte payloads × 64 streams and 16,384-byte payloads × 8 streams, each with 1,000 fixed operations per stream and no warmup. Aggregate useful request/response bytes were 131,072,000 and 262,144,000 respectively.

The exact retained binary hashes are in `environment.json`. This package copies small records, analyses and authoring scripts only. Raw PCAPs, binaries, exports and source copies remain under `C:/NBSR-build/b1-v2-packets-e2c75b59`; `external-checksums.sha256` and `external-inputs.json` identify them. All 200 raw checksums and the small package checksums were verified after the quiet benchmark completed.

## Whole-PCAP measured network layers

These totals observe the server-facing leg of an equivalent single-flow UDP relay, from verified capture readiness through setup, fixed operations, untimed validation and teardown. Only exact private readiness probe tuples with verified tokens are excluded; full packet and frame-byte inventories reconcile including probes. Readiness probes never target the QUIC endpoint.

Paired NBSR-minus-Direct bytes below are median [minimum, maximum]. Full per-path medians/ranges, paired values, sample CV and normalization are in `analysis.json`.

| Payload / streams | Captured NULL frame bytes | IP bytes | UDP bytes | UDP payload bytes |
|---|---:|---:|---:|---:|
| 1,024 / 64 | -8,276 [-90,470, 101,906] | -4,424 [-81,874, 96,866] | 13,569 [-38,894, 71,666] | 19,241 [-21,702, 61,586] |
| 16,384 / 8 | -1,279,419 [-2,139,795, 517,127] | -1,204,659 [-2,003,371, 483,907] | -830,859 [-1,321,251, 317,807] | -681,339 [-1,048,403, 251,367] |

## Relay phase counters: directly measured UDP payload and datagrams

These are separate relay counters, not a timestamp split of the PCAP. The first client tuple must match the authorized child PID through OS endpoint ownership; later datagrams must match that tuple. All 20 records have zero rejected datagrams. Relay phase transitions and counters share a lock; both client implementations require positive setup-complete, measurement-start and measurement-stop acknowledgments before successful final output. Individual ACK transcripts and phase timestamps were not retained.

**Setup** runs from relay creation through setup-complete after connection/stream preparation. Later preflight validation/materialization is in the excluded warmup phase. **Established** runs from measurement-start before fixed-operation release through measurement-stop after one postflight validation exchange per stream and 100 ms settling. It excludes teardown but is not identical to the timed measured_ns interval. Setup plus established does not equal the whole capture.

| Payload / streams | Phase | UDP payload byte delta median [range] | Datagram delta median [range] |
|---|---|---:|---:|
| 1,024 / 64 | setup | 31,049 [30,985, 31,075] | 213 [211, 214] |
| 1,024 / 64 | established | -14,423 [-56,972, 36,895] | -1,173 [-2,363, 1,054] |
| 16,384 / 8 | setup | 12,946 [12,920, 12,968] | 45 [44, 46] |
| 16,384 / 8 | established | -628,511 [-1,121,716, 265,790] | -18,641 [-34,112, 8,263] |

Setup payload-delta sample CV was 0.127% and 0.155%; established payload-delta CV was 224.3% and 89.0%. CV is descriptive and uses sample standard deviation divided by absolute mean. Near-zero signed differences make delta CV large; it is not a performance stability gate.

## Qualifications and reproduction

- Useful-byte denominators exclude untimed validation traffic. Whole-capture or established-counter ratios must not be described as fixed-operation-only overhead.
- Established IP, UDP-header and link-layer bytes remain NOT_PROVEN: no phase-aligned capture timestamps exist. NULL/Loopback frame bytes are not physical Ethernet bytes.
- The first verified-readiness smoke failed before workload release. Its raw directory remains preserved; the complete-prefix parser correction subsequently passed a four-capture smoke and this 20-capture run. See `external-inputs.json`.
- Capture command: `python scripts/run_b1_v2_capture.py --output C:/NBSR-build/b1-v2-packets-e2c75b59` (defaults: five repeats, 1,000 operations per stream).
- `analyze_records.py` and `analyze_phases.py` preserve the exact record-only derivation. They refer to the external raw root and sibling outputs; use fresh output paths when reproducing to preserve existing evidence. No external TShark reruns are required for these analyses.
- Package and raw checksum verification passed before commit. No source tests or repeat captures were required by this packaging-only change.
