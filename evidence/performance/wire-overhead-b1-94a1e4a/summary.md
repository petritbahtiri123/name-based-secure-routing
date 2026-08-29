# B1 Direct-vs-NBSR Wire Overhead

Classification: **INCONCLUSIVE**

## Measurement method

MEASURED: UDP payload bytes and UDP datagrams forwarded by a single-flow loopback relay. The relay binds a fresh loopback endpoint per run and admits a source endpoint only when OS UDP ownership identifies the authorized benchmark client PID; rejected datagrams invalidate a run.

DERIVED: IPv4+UDP network bytes add 28 bytes per measured datagram. Physical Ethernet framing, preamble, inter-packet gap, and FCS are not present on Windows loopback and are not reported as measured.

Retransmissions are NOT MEASURABLE with the available non-privileged instrumentation. Windows pktmon was present but access was denied.

Application bytes mean aggregate request plus response payload bytes; one echo operation carries two payloads.

| Payload | Streams | Valid pairs | Representative Direct measured UDP bytes | Representative NBSR measured UDP bytes | Median Direct packets | Median NBSR packets | Paired incremental bytes | Paired incremental overhead | Stability |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|:---|
| 1024 | 64 | 5 | 1403782499 | 1403809402 | 1253662 | 1253978 | 26903 | 0.0019% | difference-within-pair-dispersion |
| 16384 | 8 | 5 | 2711802076 | 2710987319 | 2516349 | 2548190 | -814757 | -0.0300% | difference-within-pair-dispersion |

## Setup/admission

- 1024 B / 64 streams: Direct 6752 bytes, NBSR 37822 bytes, delta 31070 bytes (460.16%).
- 16384 B / 8 streams: Direct 6721 bytes, NBSR 19693 bytes, delta 12972 bytes (193.01%).

Warm-up traffic is excluded. Established counters begin only after an acknowledged measurement-start marker and stop after all fixed-count operations complete.

## Previous estimate comparison

The earlier approximate 6.45–8.59% values modeled total framing/transport overhead. They were not measured incremental NBSR tax and are not directly comparable to this Direct-vs-NBSR delta.

## Environment

- Base Git SHA: `94a1e4a2da528534ce9e2c62bc9d7a6335bd81ab`
- OS: Windows-11-10.0.26200-SP0
- CPU: Intel(R) Core(TM) i5-10210U CPU @ 1.60GHz
- RAM bytes: 16942501888
- Command: `scripts/run_b1_wire_overhead.py --output evidence/performance/wire-overhead-b1-94a1e4a --repeats 5 --warmup-seconds 3`
