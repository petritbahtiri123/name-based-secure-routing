# Native lifecycle coordinator: scoped functional closure

**MEASURED: PASS_FUNCTIONAL_COORDINATOR_VALIDATION.** Release/source SHA
`3dfd9f8a57d48de8082a1bd17d35571ea7ff692d`, native Linux filesystem fixtures,
fresh Docker namespaces on one Windows/WSL host, two source shards and one
selected guest CPU per role. No physical-server/WAN/capacity claim.

| Cell | Repeats | Result |
| --- | ---: | --- |
| 16 bundles, 100 offered/s | 3 | 48/48 completed; all phases and eleven final ownership counters pass |
| 512 bundles, 100 offered/s | 5 | 2,560/2,560 completed; all phases and eleven final ownership counters pass |
| EOF after both active, source side | 3 | Endpoint fails closed; owned processes gone, no forced local relay termination |
| EOF after both active, destination side | 3 | Endpoint fails closed; owned processes gone, no forced local relay termination |

Each positive cell requires source preparation before destination start, both
complete active sets, at least two seconds of coordinator and per-host hold,
destination-first release, every source ACK, destination report readiness,
two-second cooldown, zero relay exits and independently verified raw peer data.
Socket observations join PID/start epoch/executable/FD/inode while live. An
independent post-run scan inside each namespace finds no owned measurement
executable before the fixture container is stopped.

Cancellation is a **negative** lifecycle result. Killing/reaping an owned process
does not prove its eleven runtime counters reached zero gracefully. The generic
relay cleanup report remains UNCONFIRMED on nonzero exit; the fixture's separate
in-namespace process observation establishes process absence for these cells.
This does not prove cleanup after network partition, host loss or SIGKILL.

## Retained defect and correction

The first 25db6831 release trial completed the 16-connection source workload and
emitted completion, but Python aborted with exit 134 while a daemon thread held
buffered stdin during interpreter shutdown. The coordinator correctly rejected
the nonzero relay; its evidence remains in `native-control-smoke-25db6831`.
The correction uses bounded nonblocking descriptor reads, a stop event and a
reader join before shutdown. All fourteen subsequent live cells above pass
their respective positive/negative acceptance gates.

One independent focused review also found that collecting output after failed
startup could copy an unrelated preexisting directory. A RED/GREEN regression
now requires a ledger-validated live phase before collection. Without that proof,
collection is skipped and output ownership stays unconfirmed. Scoped re-review
accepted the correction. Archive extraction separately rejects traversal,
duplicates, links, sparse/special files and oversized payloads.

## Validation and limits

107 focused Python tests pass, including actual pipe shutdown and owned-relay
EOF/deadline tests. Ruff and diff checks pass. Both fresh release builds retain
byte-identical Rust binaries to the prior accepted a1ac83c8 build; no production
Rust/Go, dependency, protocol, security or timeout change was made. Rust/Go full
suites were not rerun for these Python-only orchestration changes.

`analyze.py` rechecks complete indexes, independent endpoint/pair gates and the
management transcript. `analysis.json` retains every positive and negative
cell and explicit scope; `raw-evidence.json` binds complete raw roots by index
checksum. Reproduce analysis from the repository root with:

```powershell
python evidence/performance/v2/native-lifecycle-coordinator-3dfd9f8a/analyze.py
```

The new external coordinator/runbook uses existing authenticated SSH with strict
host-key validation. **Real SSH execution and independent physical hosts are
NOT_EXECUTED / EXTERNAL_HARDWARE_REQUIRED.** Docker exercises the private-stream
process/barrier path; it is not evidence of SSH network-failure behavior.

No forwarding throughput, strict-stable admission rate, observer-qualified
latency, per-resource allocation, same-process retention or 60/120-minute soak
is established here. Fresh-namespace 512 success does not erase earlier
reused-namespace failures. The 100/s launch span for 1024 plus the mandatory
hold exceeds the unchanged idle lifetime; that is a fixture scheduling bound,
not a production ceiling. A different offered-rate scale cell must be declared
as a different workload and retain every outcome.
