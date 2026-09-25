# Go-to-Rust Linux lifecycle subset

This is a local Linux loopback resource/lifecycle diagnostic, not a two-host,
admission-capacity, throughput, qualified soak or production federation runner.
It uses the existing secure Go peer and Rust release destination. Frozen
authentication, authorization, replay, wire and send-completion behavior remain
unchanged. The local destination-completion marker is benchmark control only.

## Build and run

Use a clean checkout at the chosen source SHA on a provisioned Linux host,
with the locked Rust/Go toolchains, Python project dependencies, Git, taskset
and lscpu. Build before starting measurements. Use native Linux storage outside
the checkout; preserve failed attempts and never reuse output directories.

```bash
set -euo pipefail
test -z "$(git status --porcelain --untracked-files=all)"
export NBSR_GO_B3_SHA="$(git rev-parse HEAD)"
export NBSR_GO_B3_ROOT="$(mktemp -d /var/tmp/nbsr-go-b3.XXXXXXXX)"
export CARGO_TARGET_DIR="$NBSR_GO_B3_ROOT/target"
rustc --version > "$NBSR_GO_B3_ROOT/rustc.txt"
cargo --version > "$NBSR_GO_B3_ROOT/cargo.txt"
go version > "$NBSR_GO_B3_ROOT/go.txt"
cargo build --locked --release --features benchmark-harness \
  --manifest-path crates/nbsr-transport/Cargo.toml --bin wp8_interop_server \
  > "$NBSR_GO_B3_ROOT/rust-build.log" 2>&1
(
  cd interop/nbsr-go-peer
  go test -race ./... > "$NBSR_GO_B3_ROOT/go-tests.log" 2>&1
  go vet ./... > "$NBSR_GO_B3_ROOT/go-vet.log" 2>&1
  go build -mod=readonly -trimpath -o "$CARGO_TARGET_DIR/release/nbsr-go-peer" \
    ./cmd/nbsr-go-peer > "$NBSR_GO_B3_ROOT/go-build.log" 2>&1
)
python3 -B - <<'PY'
import hashlib, json, os, pathlib, subprocess
root = pathlib.Path(os.environ['NBSR_GO_B3_ROOT'])
sha = os.environ['NBSR_GO_B3_SHA']
if subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip() != sha:
    raise ValueError('source changed during build; preserve and rebuild')
if subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=all']).strip():
    raise ValueError('source became dirty during build; preserve and rebuild')
target = pathlib.Path(os.environ['CARGO_TARGET_DIR']) / 'release'
manifest = dict(source_sha=sha, build_profile='release',
    binary_sha256={name: hashlib.sha256((target/name).read_bytes()).hexdigest()
        for name in ('nbsr-go-peer', 'wp8_interop_server')},
    build_commands=[['cargo', 'build', '--locked', '--release', '--features', 'benchmark-harness',
        '--manifest-path', 'crates/nbsr-transport/Cargo.toml', '--bin', 'wp8_interop_server'],
        ['go', 'build', '-mod=readonly', '-trimpath', '-o', str(target/'nbsr-go-peer'), './cmd/nbsr-go-peer']],
    toolchains={name: (root/(name+'.txt')).read_text() for name in ('rustc', 'cargo', 'go')})
with (root/'build-manifest.json').open('x') as stream:
    json.dump(manifest, stream, indent=2)
PY
python3 -B scripts/run_b3_v2.py --platform linux --path go-rust --cores 1 \
  --target "$CARGO_TARGET_DIR" --build-manifest "$NBSR_GO_B3_ROOT/build-manifest.json" \
  --axis streams --fixed-channels 1 --counts 16 32 64 --repeats 5 \
  --output "$NBSR_GO_B3_ROOT/streams"
python3 -B scripts/run_b3_v2.py --platform linux --path go-rust --cores 1 \
  --target "$CARGO_TARGET_DIR" --build-manifest "$NBSR_GO_B3_ROOT/build-manifest.json" \
  --axis channels --counts 16 32 --repeats 5 --output "$NBSR_GO_B3_ROOT/channels"
python3 -B scripts/run_b3_v2.py --platform linux --path go-rust --cores 1 \
  --target "$CARGO_TARGET_DIR" --build-manifest "$NBSR_GO_B3_ROOT/build-manifest.json" \
  --axis cycles --counts 50 --repeats 5 --output "$NBSR_GO_B3_ROOT/cycles"
python3 -B -m scripts.performance.b3_go_linux_analysis \
  "$NBSR_GO_B3_ROOT/streams" "$NBSR_GO_B3_ROOT/channels" "$NBSR_GO_B3_ROOT/cycles" \
  --output "$NBSR_GO_B3_ROOT/analysis.json"
```

The manifest is operator-supplied provenance, not compilation attestation.
Keep its build logs, commands and exact source available. Do not relabel a
previous binary with a new source SHA. Build/controller mismatch is explicitly
diagnostic. A failed cell stops that invocation, retaining partial records and
failure artifacts; it must not be silently replaced by a passing repeat.

## Interpretation and acceptance

Both roles share one topology-selected logical representative of one advertised
physical core. Inside a VM this is guest placement, not verified exclusive host
core ownership. Affinity is checked for observed threads; thread enumeration is
a snapshot and can miss threads that start and finish between observations.
Nonleader disappearance during proc reads is tolerated; leader disappearance,
access errors, wrong affinity and detected untracked child processes reject.

Only sequential channel, stream and same-process cycle axes are supported.
Go bundle fanout, materialized stream payload and Rust allocator XML are rejected.
The default Rust mode is unchanged. Five repeats are requested explicitly, so
the minimum three/five-if-CV-exceeds-5% rule does not require deleting or replacing
earlier measurements. Report all-repeat CV and retain high dispersion as a
qualification; this diagnostic analyzer does not establish stable performance.

Required functional evidence: every expected numbered response succeeds with
1024 bytes in each direction; every destination completion ordinal exists; both
owned processes exit; all eight instrumented destination counters are zero.
Go source ownership counters are **NOT_MEASURED**, even after process exit.
No eleven-counter source cleanup claim follows from this subset.

Linux private resident/RSS/PSS, separate hugetlb, FD/thread counts and identity
are sampled at the existing half-second cadence through idle/active/cooldown.
The source naturally exits before the final cooldown: final metrics are null,
bound to the previously observed process epoch and successful exit. Destination
cooldown stays live behind its report gate. No zero-memory substitution occurs.
The Go runtime series is separate and is not automatically phase-aligned.

Analyze staircase behavior across cycles and plateau/dispersion across repeats.
Live process memory is measured; allocator cause, leak attribution and isolated
bytes/connection/session/channel/stream require additional evidence. The source
stream registry does not prove remote stream/payload materialization during hold.
Observer neutrality, a stable throughput/admission ceiling and near-ceiling soak
are not acceptance outputs. Actual external/server execution remains unverified.

Evidence structure: each axis has environment/build manifests, retained binary
bytes, source snapshots, raw stdout/stderr/runtime logs, cell/cleanup/resource
records, failures when present, and `checksums.sha256`. Analysis rechecks indexed
bytes and compatible source/build/platform placement before reporting results.

Initial Linux Go sampling waits for its exclusive runtime file after exec, before any connection start marker. This prevents proc memory reads racing address-space replacement; ordinary live sampling errors still fail. See the [September 25 evidence](../../evidence/performance/v2/go-linux-lifecycle-de50692f/summary.md).
