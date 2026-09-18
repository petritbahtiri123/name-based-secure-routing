# Linux Direct/NBSR packet accounting at 6b3d37e8

Classification: MEASURED Docker/WSL Linux loopback packet accounting. Not a capacity or physical-wire result.

Five counterbalanced pairs per workload, 20 captures total: 1 KiB / 64 streams and 16 KiB / 8 streams, 1000 operations per stream, no warmup. All useful operations complete; zero workload errors/timeouts, zero rejected relay datagrams and zero reported capture losses. Every capture has exact initial/terminal marker validation and PID/start-time/socket-inode client ownership.

| Payload / streams | Useful application bytes per run | Direct median IP bytes | NBSR median IP bytes | Median paired delta | Paired delta range | Delta / useful app bytes |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 1024 / 64 | 131072000 | 143818388 | 144920158 | 1192910 | 836011 .. 1519934 | 0.910118% |
| 16384 / 8 | 262144000 | 274541726 | 274411311 | -117313 | -280129 .. -28622 | -0.044751% |

MEASURED IP/UDP lengths cover the whole capture: setup, useful fixed operations, matched untimed validation and teardown. Useful application bytes exclude untimed exchanges. These observed paired deltas include secure-transport packetization/scheduling variability; they are not a constant NBSR wire-format tax. No selected favorable pair substitutes for the cohort.

| Payload / streams | Direct IP-byte CV | NBSR IP-byte CV | Direct packet-count CV | NBSR packet-count CV |
| --- | ---: | ---: | ---: | ---: |
| 1024 / 64 | 0.0506% | 0.1977% | 1.2049% | 4.7361% |
| 16384 / 8 | 0.0363% | 0.0262% | 1.7321% | 0.5272% |

All UDP, payload, packet-count and synthetic captured-frame totals/deltas/CVs are retained in packet-summary.json. Physical Ethernet including FCS/preamble/IFG is NOT_MEASURED. Established-only packet phase accounting, retransmission attribution and performance observer qualification are NOT_PROVEN. Capture timing is DIAGNOSTIC_ONLY; CPU/memory resources were not sampled for a capacity claim.

## Separate relay phases

The relay counts UDP payload at its existing acknowledged setup/established barriers. This is not the same scope as the full pcap. Derived IPv4 estimates in relay-summary.json remain DERIVED, while pcap IP lengths above are MEASURED.

| Payload / streams | Median setup UDP payload delta | Established median paired UDP payload delta | Established delta range |
| --- | ---: | ---: | ---: |
| 1024 / 64 | 30949 | 365318 | 179151 .. 496496 |
| 16384 / 8 | 12793 | -6536 | -89265 .. 34379 |

## Preserved failures and measured harness correction

The initial controlled UDP fixture failed metadata matching on Capinfos' exact Ethernet suffix, then showed why immediate shutdown missed final packets even with reported zero drops. A distinct captured terminal marker closes that measurement gap. The corrected two-packet fixture passed. Literal RED/GREEN tests cover these cases; Windows NULL/Loopback remains the default.

At eb4b0608, the mechanics smoke completed four captures. The first formal cohort retained one complete Direct run (105168 captured, zero drops) and an invalid NBSR capture (122221 captured, 845 pcap drops). No complete matched pair was accepted. This unfavorable predecessor is retained separately and is not merged into the new cohort.

The minimal observer correction requests a bounded 64 MiB kernel capture buffer instead of Dumpcap's documented 2 MiB default. Both paths use the same request, unchanged workload and timeouts. Fresh release builds at eb4b0608 and 6b3d37e8 produce identical binary hashes. The new cohort has zero observed drops; this does not guarantee lossless capture at other loads. No production NBSR optimization or security/wire change was made.

## Environment and verification

Debian 12 capture tools, Wireshark 4.0.17, Docker Desktop/WSL. Capture ran as root only inside the disposable container with its default capabilities; no Windows elevation, host security-policy change or added container privilege was used. Dumpcap prints cap_set_proc warnings, retained verbatim; acceptance depends on actual packet/drop/marker evidence. This is not native Linux/server, physical NIC, independent-operator federation or host/root security evidence.

Focused Python regression tests and Ruff logs are retained. The full raw recursive indexes bind pcapng, exports, commands, release binaries, build manifests, tool/image metadata, failed attempts and source patches. Raw locations and exact index hashes are in raw-evidence.json. All canonical/raw checksums and canonical privacy must pass before commit.

Reproduction: docs/benchmarks/B1_LINUX_PACKET_ACCOUNTING.md. Existing administrator/native-server/soak/authority blockers remain separate. No new stable/degraded/saturated throughput or admission boundary is established by this stage.
