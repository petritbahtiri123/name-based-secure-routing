# B3: 32-channel stream residency through 2048

MEASURED at clean b29054b9, Windows loopback, release binaries. All 35 cells
passed: five repeats each at 32/64/128/256/512/1024/2048 streams, 32 fixed channels,
one connection/session, 1 KiB held request per stream. Both endpoint ready
snapshots prove exactly the named application/Quinn stream count before common
release; all 20,320 expected stream completions validated payload and response/ACK
behavior. All eleven final ownership counters are zero on both roles in every
cell. All 325 raw artifact hashes verified. This is a memory/residency workload;
its explicit hold makes request timing unsuitable for forwarding-latency claims.

| Streams | Source active private bytes, median | Destination active private bytes, median | Source / destination CV |
|---|---:|---:|---|
|32|2461696|2686976|1.505% / 1.207%|
|64|3063808|3321856|0.416% / 0.540%|
|128|4349952|4718592|0.287% / 0.770%|
|256|6934528|7364608|0.193% / 0.569%|
|512|12140544|12779520|0.146% / 0.227%|
|1024|22007808|22904832|0.726% / 0.196%|
|2048|42516480|44367872|0.243% / 0.099%|

DERIVED process-private slopes over these count medians: source 19,848.84 and
destination 20,624.50 bytes per additional held stream, combined 40,473.34 bytes.
The combined active-minus-idle slope is 40,467.97 bytes/stream. These include
runtime, QUIC, allocator and fixture costs; they are not pure NBSR object sizes,
allocation counts or wire overhead. Baselines, ranges and repeat gates remain
in analysis.json. At 2048 the two roles together held 86,884,352 median private
bytes. The configured 32-channel series is separate from the earlier 8-channel
series and must not be pooled into one regression.

The workload reaches the existing 2048 application-stream fixture budget beneath
the transport's 2049 bidirectional streams including control. No protocol or
transport limit was raised. This is not a host-memory ceiling, global production
stream/session limit or external/server result. Same-process cycle evidence is
separately bound at a6d46796 in ../b3-materialized-scale-a6d46796/REPORT.md;
no new cycle result is inferred from these fresh-process scale cells.

Two audit-consumer harness gaps and their failed attempts remain preserved in
../b3-audit-consumer-36e8970b/ and ../b3-materialized-accept-audit-546b4920/.
Mandatory audit generation, full-queue rejection, authentication, authorization,
ACCEPT, wire/crypto, payload and send-completion semantics remain intact.
Private-retention/allocator cause remains INCONCLUSIVE; zero tracked ownership
does not prove zero untracked allocations.

Reproduce from the exact recorded release source with a fresh output directory:

```powershell
$env:CARGO_TARGET_DIR='C:/NBSR-build/b4b-task4k'
cargo build --release --locked --manifest-path crates/nbsr-transport/Cargo.toml --features benchmark-harness --bin perf_rust_source --bin wp8_interop_server
python scripts/run_b3_v2.py --output C:/NBSR-build/b3-wide-reproduction --target C:/NBSR-build/b4b-task4k --axis streams --fixed-channels 32 --counts 32 64 128 256 512 1024 2048 --repeats 5 --materialized-streams
```

The runner copies existing binaries; verify its retained source/binary hashes.
Raw evidence at the external-input.json path is authoritative and must not be
removed as disposable build data. No builds, tests or Docker workloads ran during
measurement; lightweight read-only inspection/planning continued.
