# Native-address finite peer validation

MEASURED: 16 valid finite cells across two isolated Docker network namespaces,
with distinct 172.20.0.2/172.20.0.3 addresses, UID 65532 and identical release
binaries/source 1d24cb4c740c53c945932ff8d67bdd34b3b75209. Three-second warmup,
20-second measurement, depth one, one reported guest core per peer. The pools
overlap on one Docker/WSL host. This is functional transport/runner evidence,
not independent-server, physical-NIC or strict-stable capacity evidence.

| Shape | Counterbalanced pairs | Direct median Gbit/s | NBSR median Gbit/s | Direct/NBSR CV |
|---|---:|---:|---:|---:|
| 1 KiB, 64 streams | 5 | 1.503628 | 1.780496 | 10.092% / 2.475% |
| 16 KiB, 8 streams | 3 | 2.808782 | 2.955203 | 0.229% / 1.938% |

These rates are DIAGNOSTIC. Observer cost is NOT_QUALIFIED; residual Direct
dispersion remains after five pairs. They do not establish a Direct/NBSR
performance advantage. All sixteen source validity contracts passed with zero
errors, missing, duplicate, corrupt or wrong responses and zero measured
session/channel/stream/replay creation deltas. All 32 peer exits were zero and
retained a terminal zombie sample before reaping. Runtime eleven-counter
ownership cleanup was NOT_MEASURED; process exit is not a substitute.

The affinity negative control changed only the owned source peer's affinity.
The sampler rejected the mismatch, killed its owned process group and reaped
exit -9, with no accepted result or completion ACK. Destination exit was zero;
it does not turn the failed source workload into a successful cell.

The fresh untrusted-authority control produced HandshakeFailed on both peers,
nonzero source exit and no accepted source result/ACK. Its original diagnostic
controller expected a detailed certificate error string and failed; that
assertion, traceback and raw attempt remain preserved. Detailed TLS issuer
attribution is INCONCLUSIVE. This is not a replacement for the accepted full
security matrix. Neither negative attempt is included as a performance repeat.

The implementation has literal RED and focused GREEN evidence. The mistaken
intermediate pytest filename/no-tests run is retained. Final focused verification:
33 Python tests, Ruff and diff checks PASS. No production transport/security
optimization, protocol change, deadline increase or workload reduction occurred.

Raw indices bind every peer output, command, setup/controller log, binary copy,
resource sample, container/network description and failed diagnostic. Private
test keys were kept outside publishable evidence. External hardware, full remote
matrix, qualified soak and B5 causal attribution remain open.
