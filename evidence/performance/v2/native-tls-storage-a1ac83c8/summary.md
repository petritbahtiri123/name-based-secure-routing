# Native TLS fixture storage comparison

Source: `a1ac83c8431836d5cd2b4a9bd04a7947a2a71a3b`, release binaries unchanged
from a401567d. Five counterbalanced pairs, 512 held bundles/cell, 100 offered/s,
two source shards, one guest CPU per role, 1 KiB materialized streams. Each cell
uses fresh owned containers and separate native control roots. The two arms use
identical public fixture bytes within each pair; generated private fixture copies
remain outside public evidence. Both arms create a native TLS copy before the run,
and differ only in which authority directory the peers read. Output remains on
the Windows mount. Source preparation and local watcher socket checks are common.

**All ten cells complete 512/512: 5,120 connections, both-endpoint active/release,
source ACKs and all eleven final ownership counters zero.** Independent peer-pair
validation accepts all ten. Named marker inventories and live PID/start/executable/
FD/socket bindings are checked separately; the controller records at least two
seconds between observing both endpoints active and starting release.

| Diagnostic cold-handshake timer | Windows-mounted TLS | Native Linux TLS |
| --- | ---: | ---: |
| Median cell p50 | 12.120 ms | 2.890 ms |
| Median cell p95 | 333.631 ms | 88.588 ms |
| Median cell p99 | 450.859 ms | 147.607 ms |
| Across-cell p99 CV | 87.574% | 65.889% |

Quantiles use nearest rank within each cell and the median across five cells.
All three displayed quantiles are lower with native TLS in every matched pair.
The raw `transport_handshake_ns` field begins **before synchronous TLS fixture
reads/configuration**, not immediately at QUIC connect. This supports harness
fixture-I/O sensitivity in cold-start measurement; it does not measure a pure
network/TLS handshake speedup. Variability is large and timing is diagnostic only.
There is no strict-stable admission or forwarding claim and no production change.

This fresh-per-cell fixture now has five fully successful 512-bundle repeats in
each arm. Earlier reused-namespace 512 cohorts remain PARTIAL at 3/5; their valid
failures are not pooled away, replaced, or retroactively passed. Freshness also
differs between these cohorts, so this comparison does not attribute every
earlier failure to TLS storage or prove that namespace reuse is its cause.
General 512 repeatability across lifecycle/host conditions remains unresolved.

An earlier mounted-TLS preview reached all 512 active around 8.5 seconds after
process sampling began, then failed during hold/release against the unchanged
idle lifetime. Its cancellation exceeded the existing wait and its owned
containers were stopped; no cleanup pass is claimed. That partial failed cell is
retained separately and yielded no TLS pair. The first isolated-controller setup
also failed before launching any peer because its private parent directory did
not exist. The corrected controller uses a new root, creates that parent, records
each trial before launch, and always stops/verifies only its owned containers
before proceeding. No benchmark/transport timeout was enlarged.

No 1024-cell run follows: at unchanged 100/s, nominal launch span plus the required
hold exceeds the existing idle lifetime. This is a fixture limitation, not a
production memory/connection ceiling. Same-process retention, sustained admission,
physical-core efficiency, external hardware and qualified soak remain separate.

`raw-evidence.json` retains the completed comparison, both earlier failures,
analysis and exact release build. `analysis.json` binds every pair verdict,
fixture agreement and per-cell quantiles. TLS keys and private fixture copies are
not published. Checksum indexes provide integrity, not host attestation.
