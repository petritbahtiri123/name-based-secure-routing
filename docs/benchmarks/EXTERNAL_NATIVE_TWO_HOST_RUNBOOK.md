# Native Linux two-host finite Direct/NBSR runbook

An executable replacement for this document's inline per-host observer is now
available: [finite native peer execution](EXTERNAL_NATIVE_PEER_EXECUTION.md).
Use its checked source/build/role interface for new runs. The legacy inline
wrapper below remains an authored historical procedure, not executed evidence.

**AUTHORED / NOT_EXECUTED ON EXTERNAL HARDWARE.** This procedure covers one
finite established-forwarding shape on two operator-controlled Linux hosts.
It is not full Task 8 acceptance. Six accepted Docker Desktop loopback controls
at `3644c324a535586e89af72a8c9796e8d58fadf48` establish VM compatibility only;
they do not validate these remote commands, NICs, physical servers, or a speedup.

## Preconditions and source binding

Use the same reviewed commit containing the benchmark bind flags on both hosts.
Do **not** use `3644c324` as the external execution SHA: that older commit lacks
the flags. Record the final full SHA after their tests/review and commit. Build
from clean native checkouts, keeping each checkout and its `vectors/` directory
present at its original build path (the fixtures use `CARGO_MANIFEST_DIR`).

The benchmark-only options are:

- Source: `--benchmark-client-bind SOURCE_IPV4:0`.
- Destination: `--benchmark-listen DESTINATION_IPV4:PORT`; port 0 is allowed and
  the actual port must then be obtained from readiness.
- Both require a concrete unicast IPv4 address. Unspecified, multicast,
  limited-broadcast (`255.255.255.255`), IPv6, malformed and duplicate options
  are rejected. Directed-subnet broadcast cannot be identified from a bare IPv4
  address without its netmask; operators must exclude it. Explicit
  listen conflicts with `NBSR_TASK10B_CAPTURE_PORT`; remove that experiment mode.
- TLS identities remain `source.edge` and `destination.edge`. An IP endpoint
  does not replace the certificate name or authorize disabling verification.

The addresses must already exist on their respective hosts, and the selected
UDP destination port must already be permitted on the intended test network.
Use an existing authenticated SSH/SCP relationship for artifact and ACK transfer;
do not disable host-key verification. This runbook changes no firewall, sysctl,
transport deadline, buffer, authentication, or authority rule.

GNU coreutils `timeout` is required on the management-command host. Every SSH
and SCP operation below has an outer execution bound, including after successful
authentication. Record `timeout --version` with the host inventory. A timed-out
management operation rejects the cell; retain all partial evidence and do not
retry it as a successful repeat. These bounds do not extend Direct's existing
30-second protocol ACK budget.

On each host, set these operator-specific values. Use fresh absolute paths
without whitespace, quotes or shell metacharacters, because the SSH examples
include remote shell paths. Do not reuse a failed cell directory.

```bash
set -euo pipefail
export REPO=/srv/nbsr/repository
export SOURCE_SHA=REPLACE_WITH_REVIEWED_40_HEX_COMMIT
export BUILD=/srv/nbsr/build-native-$SOURCE_SHA
export RUN=/srv/nbsr/evidence/native-two-host-RUN_ID
export AUTH=/srv/nbsr/private/native-authority-RUN_ID
export SOURCE_IPV4=REPLACE_WITH_SOURCE_INTERFACE_IPV4
export DESTINATION_IPV4=REPLACE_WITH_DESTINATION_INTERFACE_IPV4
export PORT=44444
export CPUS=REPLACE_WITH_LOCAL_CPU_LIST
export WORKERS=1
export STREAMS=64
export DEPTH=1
export PAYLOAD=1024
export WARMUP=3
export DURATION=20
umask 077
mkdir "$RUN"                         # Must fail if evidence already exists.
cd "$REPO"
test "$(git rev-parse HEAD)" = "$SOURCE_SHA"
test -z "$(git status --porcelain --untracked-files=all)"
export CARGO_TARGET_DIR="$BUILD"
rustc -Vv > "$RUN/rustc.txt"
cargo -V > "$RUN/cargo.txt"
python3 --version > "$RUN/python.txt"
cargo build --release --locked --manifest-path crates/nbsr-transport/Cargo.toml \
  --features benchmark-harness --bin perf_direct_peer --bin perf_rust_source \
  --bin wp8_interop_server > "$RUN/build.stdout" 2> "$RUN/build.stderr"
test $? -eq 0 || exit 1
export BIN="$BUILD/release"
sha256sum "$BIN/perf_direct_peer" "$BIN/perf_rust_source" \
  "$BIN/wp8_interop_server" > "$RUN/binaries.sha256"
git rev-parse HEAD > "$RUN/source.sha"
git status --porcelain --untracked-files=all > "$RUN/source-status.txt"
```

Use recorded project-compatible toolchains. The accepted Linux image used Rust
1.97.1 and Python 3.14.6. Install the existing hash-pinned Python dependencies in
an external venv **before timing**, or verify an equivalent prepared environment:

```bash
python3 -m venv "$BUILD/python"
export PY="$BUILD/python/bin/python"
"$PY" -m pip install --only-binary=:all: --require-hashes \
  -r "$REPO/deploy/isp-federation-poc/requirements.lock" \
  > "$RUN/python-install.stdout" 2> "$RUN/python-install.stderr"
test $? -eq 0 || exit 1
"$PY" -m pip check > "$RUN/python-check.txt"
"$PY" -m pip freeze > "$RUN/python-packages.txt"
export PYTHONPATH="$REPO"
```

## Fresh test authority and host inventory

On a trusted preparation host, generate the existing one-day test authority
once, shortly before the campaign:

```bash
test ! -e "$AUTH" && test ! -L "$AUTH" || exit 1
"$PY" - "$AUTH" <<'PY'
from pathlib import Path
import sys
from scripts.performance.authority import write_loopback_authority
write_loopback_authority(Path(sys.argv[1]))
PY
chmod 700 "$AUTH"
chmod 600 "$AUTH"/*
```

Despite its helper name, the certificates use DNS SAN peer identities, not IP
SANs. Transfer `ca.der`, `source.der`, `source-key.der` to the source host and
`ca.der`, `destination.der`, `destination-key.der` to the destination host's
fresh `$AUTH` directory using authenticated SCP. Create remote directories with
mode 700 and files with mode 600. Do not include private keys in public evidence,
stdout, reports or command arguments. The helper does not persist the CA key.
Complete both paths before the certificates expire; preserve which certificate
fingerprints were used without silently switching authority within a cohort.

For example, when preparation runs on the source host (which retains the fresh
authority directory), install only the destination's subset remotely:

```bash
export DEST_SSH=REPLACE_WITH_EXISTING_SSH_ALIAS
export DEST_AUTH=/srv/nbsr/private/native-authority-RUN_ID
timeout --signal=KILL 10s ssh -o BatchMode=yes "$DEST_SSH" "umask 077; mkdir '$DEST_AUTH'"
timeout --signal=KILL 10s scp -o BatchMode=yes "$AUTH/ca.der" "$AUTH/destination.der" \
  "$AUTH/destination-key.der" "$DEST_SSH:$DEST_AUTH/"
timeout --signal=KILL 10s ssh -o BatchMode=yes "$DEST_SSH" \
  "chmod 700 '$DEST_AUTH'; chmod 600 '$DEST_AUTH/ca.der' '$DEST_AUTH/destination.der' '$DEST_AUTH/destination-key.der'"
sha256sum "$AUTH/ca.der" "$AUTH/source.der" "$AUTH/destination.der" \
  > "$RUN/certificate-fingerprints.sha256"
```

Set destination `AUTH` to `DEST_AUTH`. Parent directories must already exist;
the exclusive `mkdir` failure stops reuse. The source's preparation directory
contains the destination key too and must remain private.

On both hosts, retain the following before timing:

```bash
uname -a > "$RUN/uname.txt"
timeout --version > "$RUN/timeout-version.txt"
lscpu -J > "$RUN/lscpu.json"
ip -j address > "$RUN/addresses.json"
ip -j route > "$RUN/routes.json"
cat /proc/self/status > "$RUN/controller-status.txt"
taskset -pc $$ > "$RUN/controller-affinity.txt"
```

Also record NIC/driver/link speed/MTU and VM/container status when available;
mark unavailable fields explicitly. Choose one allowed logical CPU from each
distinct physical `(socket, core)` on one NUMA node using the recorded topology,
excluding SMT siblings. For this initial shape choose **one** CPU per host and
`WORKERS=1`. Numeric CPU IDs need not match across hosts. CPU quota, cgroup and
virtualization limits must be recorded; CPU pinning alone proves no hardware
ceiling. Do not alter topology or affinity between Direct and NBSR repeats.

## Per-host resource wrapper

Save the following as `$RUN/observe.py` on each host. It reuses the committed
Linux sampler, retains every sample and terminal lifetime CPU before reaping,
and verifies each sampled thread's affinity. Its 120-second bound is an
out-of-band controller limit for the specified 3+20-second finite cell, not a
transport timeout. An error rejects the cell and preserves raw output.

```python
import json, pathlib, subprocess, sys, time
from scripts.performance.linux_loopback import parse_cpu_list, sample_process

out = pathlib.Path(sys.argv[1])
cpus = sorted(parse_cpu_list(sys.argv[2]))
binary = pathlib.Path(sys.argv[3]).resolve()
argv = ['taskset', '--cpu-list', ','.join(map(str, cpus)), *sys.argv[3:]]
out.mkdir(exist_ok=False)
(out/'command.json').write_text(json.dumps(argv, indent=2))
proc = None
try:
    with (out/'stdout').open('xb') as stdout, (out/'stderr').open('xb') as stderr, \
         (out/'resources.ndjson').open('x') as resources:
        proc = subprocess.Popen(argv, stdout=stdout, stderr=stderr)
        (out/'pid.json').write_text(json.dumps({'pid':proc.pid}))
        until = time.monotonic() + 5
        while (pathlib.Path('/proc')/str(proc.pid)/'exe').resolve() != binary:
            if time.monotonic() >= until:
                raise RuntimeError('taskset/exec unavailable; see raw stderr')
            time.sleep(.001)
        deadline = time.monotonic() + 120
        identity = None
        while True:
            sample = sample_process(proc.pid, cpus)
            current = (sample['pid'], sample['start_ticks'])
            if identity is not None and current != identity:
                raise RuntimeError('process identity changed')
            identity = current
            resources.write(json.dumps(sample) + '\n'); resources.flush()
            if sample['state'] == 'Z':
                code = proc.wait(timeout=5)
                (out/'exit.json').write_text(json.dumps({'exit_code':code,'final_sample':sample}))
                if code != 0:
                    raise RuntimeError('peer exited unsuccessfully')
                break
            if time.monotonic() >= deadline:
                raise RuntimeError('finite-cell controller deadline')
            time.sleep(.1)
except BaseException as error:
    (out/'failure.json').write_text(json.dumps({'error_type':type(error).__name__, 'error':str(error)}))
    raise
finally:
    if proc is not None and proc.poll() is None:
        proc.kill(); proc.wait(timeout=5)
```

Run from `$REPO` with `PYTHONPATH` set. Keep the wrapper outside the checkout so
the source tree remains clean. Its authored commands have not been run remotely.
This wrapper records process exit and final CPU, **not eleven-counter runtime
ownership cleanup**. It records RSS, not allocator/private-heap attribution.
Resource timestamps are host-local monotonic readings; do not subtract clocks
across hosts or derive cross-host one-way latency from them.

## One matched cell: destination first, then source

Use `CELL=direct-r1` or `CELL=nbsr-r1`, with new directories on both hosts.
Keep `$RUN` existing but let the wrapper create `$RUN/$CELL` exclusively. Remove
inherited `NBSR_*` experimental environment settings before launching either
peer; only the NBSR destination's explicit `NBSR_P2A_STREAMS` is needed here.

On the **destination**, select exactly one command:

```bash
export CELL=direct-r1
"$PY" "$RUN/observe.py" "$RUN/$CELL" "$CPUS" "$BIN/perf_direct_peer" \
  --role server --authority-dir "$AUTH" --ready "$RUN/$CELL/ready.json" \
  --connections 1 --requests-per-connection 1 --p2a-streams "$STREAMS" \
  --p2a-runtime-workers "$WORKERS" --completion-ack "$RUN/$CELL/completion.ack" \
  --benchmark-listen "$DESTINATION_IPV4:$PORT"
```

```bash
export CELL=nbsr-r1
NBSR_P2A_STREAMS="$STREAMS" "$PY" "$RUN/observe.py" "$RUN/$CELL" "$CPUS" \
  "$BIN/wp8_interop_server" --authority-dir "$AUTH" \
  --ready "$RUN/$CELL/ready.json" --result "$RUN/$CELL/server-result.json" \
  --completion-ack "$RUN/$CELL/completion.ack" --p2a-runtime-workers "$WORKERS" \
  --benchmark-listen "$DESTINATION_IPV4:$PORT"
```

Leave that terminal attached; use the source terminal for the next step. On the
**source**, set `DEST_SSH=user@destination-management-host` and `DEST_RUN` to the
destination's absolute run root. Transfer readiness only after the destination
has created it, with a bounded preflight rather than assuming port availability:

```bash
export DEST_SSH=REPLACE_WITH_EXISTING_SSH_ALIAS
export DEST_RUN=/srv/nbsr/evidence/native-two-host-RUN_ID
export MODE=direct                      # direct or nbsr; match destination.
export REPEAT=1
export CELL="$MODE-r$REPEAT"             # Same cell as destination.
until_time=$((SECONDS+30))
while true; do
  remaining=$((until_time-SECONDS))
  test "$remaining" -gt 0 || exit 1
  test "$remaining" -le 3 || remaining=3
  if timeout --signal=KILL "${remaining}s" ssh -o BatchMode=yes -o ConnectTimeout=3 "$DEST_SSH" \
    "test -s '$DEST_RUN/$CELL/ready.json'"; then
    break
  else
    status=$?
    test "$status" -eq 1 || exit "$status"  # Only absent readiness retries.
  fi
  sleep .1
done
timeout --signal=KILL 5s scp -o BatchMode=yes "$DEST_SSH:$DEST_RUN/$CELL/ready.json" "$RUN/$CELL.ready.json"
export ENDPOINT=$("$PY" - "$RUN/$CELL.ready.json" "$DESTINATION_IPV4" <<'PY'
import json,sys
v=json.load(open(sys.argv[1])); host,port=v['endpoint'].rsplit(':',1)
assert host == sys.argv[2] and 0 < int(port) <= 65535
assert v['alpn'] == 'nbsr-quic-1'
print(v['endpoint'])
PY
)
test -n "$ENDPOINT" || exit 1
```

Run the appropriate source command, retaining the same parameters for both
paths. If any command fails, stop and retain the failed cell; never create its
completion ACK or replace that repeat silently.

```bash
case "$MODE" in
  direct) client=("$BIN/perf_direct_peer" --role client --lifecycle warm) ;;
  nbsr) client=("$BIN/perf_rust_source") ;;
  *) echo 'Unknown MODE' >&2; exit 1 ;;
esac
"$PY" "$RUN/observe.py" "$RUN/$CELL" "$CPUS" "${client[@]}" \
  --samples 1 --authority-dir "$AUTH" \
  --endpoint "$ENDPOINT" --benchmark-client-bind "$SOURCE_IPV4:0" \
  --payload-bytes "$PAYLOAD" --p2a-streams "$STREAMS" \
  --p2a-outstanding-per-stream "$DEPTH" --p2a-runtime-workers "$WORKERS" \
  --p2a-warmup-seconds "$WARMUP" --p2a-duration-seconds "$DURATION"
```

Immediately after the selected source succeeds, validate and ACK:

```bash
test $? -eq 0 || exit 1
"$PY" - "$RUN/$CELL" <<'PY'
import json,pathlib,sys
from scripts.performance.p2a_established import validate_repeat
p=pathlib.Path(sys.argv[1]); row=json.loads((p/'stdout').read_text().strip().splitlines()[-1])
assert validate_repeat(row) and row['measured_ns'] > 0
assert json.loads((p/'exit.json').read_text())['exit_code'] == 0
(p/'validated-result.json').write_text(json.dumps(row,indent=2))
PY
test $? -eq 0 || exit 1
timeout --signal=KILL 5s ssh -o BatchMode=yes -o ConnectTimeout=3 "$DEST_SSH" \
  "test ! -e '$DEST_RUN/$CELL/completion.ack' && : > '$DEST_RUN/$CELL/completion.ack'"
test $? -eq 0 || exit 1
```

Direct's existing destination waits up to **30 seconds** for this ACK after
connection completion. Keep transfer latency within that deadline; do not
increase it. The single-group `NBSR_P2A_STREAMS` branch currently writes its
result, closes and returns **without waiting for this ACK**. Its marker is
controller bookkeeping only, not proof of a destination wait. Confirm both
destination wrapper exit 0 and source wrapper exit 0. For NBSR require
`server-result.json` status `PASS` and the requested stream count. Its echoed
frames include preflight/warmup/measurement/postflight and must not be equated
with the source's measured-operation count.

## Repeats, evidence and acceptance

Run three matched pairs with order Direct/NBSR, NBSR/Direct, Direct/NBSR. Use
`r1`, `r2`, `r3` directories. Calculate each path's sample standard deviation
divided by its mean measured application goodput. If **either** CV exceeds 5%,
run both `r4` and `r5`, continuing alternate order; retain all five even if the
later CV falls. Any failed repeat stays rejected in the campaign inventory.
Do not lower load, remove unfavorable rows, substitute authority or mix SHAs.
If five-repeat CV remains above 5%, report dispersion; never imply strict
stability from completed bytes alone.

Compute per-repeat application Gbps as
`16 * payload_bytes * completed_operations / measured_ns`. The factor 16 counts
request and response bytes and converts to bits; nanoseconds cancel the Giga
factor. Record median/range/CV separately by path. Do not merge remote results
with Docker loopback results or claim paired effects without checking topology,
transport parameters, binary identity and repeat order.

Preserve each host's `source.sha`, clean status, binary hashes, toolchains,
topology/NIC inventory, command arrays, readiness, stdout/stderr, resource NDJSON,
terminal/exit records, validation results and ACK artifacts. Transfer destination
evidence into a separate `destination/` tree after timing; never overwrite the
source tree. Keep private authority material outside publishable evidence.
Generate hashes on each stopped, complete evidence tree:

```bash
"$PY" - "$RUN" <<'PY'
import hashlib,pathlib,sys
p=pathlib.Path(sys.argv[1]); index=p/'checksums.sha256'
with index.open('x') as out:
    for f in sorted(p.rglob('*')):
        if f.is_file() and f != index:
            with f.open('rb') as data:
                h=hashlib.file_digest(data,'sha256').hexdigest()
            out.write(f'{h}  {f.relative_to(p).as_posix()}\n')
PY
(cd "$RUN" && sha256sum --check checksums.sha256)
```

Capture final `git rev-parse HEAD` and clean status before sealing the index;
reject source drift. Record the stdout of verification and the index's own
actual-byte hash in the receiving campaign package. Preserve failures and exact
owned paths; this procedure authorizes no broad cleanup.

## Remaining portable execution gaps

This finite procedure does not complete admission/burst scheduling, per-axis
materialized B3 memory/cycle sampling, paced B5 soak with current strict-stable
reference and live resource/drift guards, or B1 wire accounting. Existing
Windows controllers use Windows affinity/resource APIs and loopback fixtures;
`linux_loopback.py` owns both local processes and explicitly rejects remote
endpoints. Do not point those controllers at remote addresses and call them
portable without implementing and testing their ownership/orchestration paths.

Before full external acceptance, implement and independently review native
two-host orchestration for those axes; establish Linux memory/ownership and
host-power availability honestly; bind each soak to the same source/binaries,
physical placement and shape; and validate remote packet-capture ownership,
readiness, packet loss, phase boundaries and measured link-layer scope.
Allocator attribution, thermal behavior, saturation/backlog gates, admission
diagnostics, and a complete payload/core/depth matrix remain explicit separate
gates. **Full Task 8 status remains PARTIAL / EXTERNAL EXECUTION REQUIRED.**

Source basis: `scripts/performance/linux_loopback.py` (`build_commands`,
`sample_process`, `run_cell`, `repeat_target`), `scripts/performance/authority.py`,
`scripts/performance/p2a_established.py`, and the benchmark source/destination
branches in `perf_direct_peer.rs`, `perf_rust_source.rs`, `wp8_interop_server.rs`.
The new bind flags must be committed and verified before executing this runbook.
