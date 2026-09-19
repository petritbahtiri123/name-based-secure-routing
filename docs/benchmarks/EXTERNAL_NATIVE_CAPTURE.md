# Bounded native-interface capture coordinator

This command owns only dumpcap and a separate UDP marker socket. It does not
launch NBSR, alter NIC/offload/firewall settings, authorize remote peers, send a
completion ACK, or replace the native peer/pair/cohort gates. Run only on the
dedicated test interface between authorized fixture hosts. Capture permission
may require root or an existing dumpcap capability; unavailable permission is
ADMIN_REQUIRED, not grounds for disabling a security control.

Prerequisites: clean reviewed source checkout, Python, dumpcap, TShark, five GiB
free space, exact destination readiness endpoint and interface MTU. Use the same
reviewed SHA for peers/capture, with release binaries from the native peer
runbook. Keep all output outside the checkout and private authority directories.
The marker receiver port must differ from the QUIC server port. On destination,
bind a separate bounded UDP discard fixture on that port before capture. For
example, replace the documentation address with the isolated test address:

```bash
python3 - 192.0.2.20 44000 <<'PY'
import socket,sys,time
with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as sock:
    sock.bind((sys.argv[1],int(sys.argv[2])));sock.settimeout(.5)
    print('PROBE_RECEIVER_READY',flush=True)
    deadline=time.monotonic()+120
    while time.monotonic()<deadline:
        try: sock.recvfrom(65535)
        except TimeoutError: pass
PY
```

After destination QUIC readiness, start the following on source in its own
terminal/job. Use actual addresses/interface/MTU and a fresh output path:

```bash
python3 -B -m scripts.performance.linux_native_capture \
  --output /absolute/campaign/capture-r1 \
  --interface eth0 --mtu 1500 --local-address 192.0.2.10 \
  --server 192.0.2.20:42000 --probe-port 44000
```

The coordinator must wait for `capture-ready.json` containing
`START_MARKER_OBSERVED` before launching the source peer. The live reader has
already observed the exact private marker tuple/token in the open pcapng.
The ready marker is published by same-directory atomic rename after JSON close;
polling must not depend on a partially written marker becoming parseable later.
Run the existing native peers with matched `--operations-per-stream 1000` and
depth one. Preserve their own output roots. Source result validation, then the
unchanged Direct completion ACK, then destination wrapper success remain the
coordinator's responsibility. Do not stop capture merely because CONNECT or
transport readiness succeeded, or while a peer is still running.

After both peers have successfully exited and their existing validity checks
pass, request capture closure atomically from the capture host:

```bash
python3 - /absolute/campaign/capture-r1 <<'PY'
import json,os,pathlib,sys
p=pathlib.Path(sys.argv[1]);ready=json.loads((p/'capture-ready.json').read_text())
assert ready['status']=='START_MARKER_OBSERVED'
assert not (p/'capture-stop.json').exists()
with (p/'capture-stop.tmp').open('x') as f: json.dump({'token':ready['token']},f)
os.replace(p/'capture-stop.tmp',p/'capture-stop.json')
PY
```

Wait for capture wrapper exit zero and its sealed `result.json`; an existing
ready/stop file alone is not successful evidence. Any peer/capture failure
invalidates the comparison. Preserve the failed attempt; do not replace it.
The random stop token prevents an old marker from closing a new attempt, but is
not an authentication protocol or proof that the operator verified the peers.
Bind and validate both complete peer roots separately using the pair/cohort
commands in EXTERNAL_NATIVE_PEER_EXECUTION.md.

The retained ec255c18 Docker experiment isolates a capture representation issue:
three matched Direct on/off pairs show oversized IPv4 aggregates only while
`tx-udp-segmentation` is enabled on the private veths. The MTU rejection stays
unchanged. This does not establish physical NIC behavior, physical wire bytes,
or a production performance improvement. Test-specific offload configuration
and its before/after inventory belong to the external coordinator; this capture
command does not change them. The initial paired cohort stops at its unchanged
five-GiB disk reserve and remains INVALID_PARTIAL; see
[the retained attribution evidence](../../evidence/performance/v2/native-offload-ec255c18/summary.md).

The wrapper observes a distinct terminal token before stopping/reaping its own
capture child. Complete inventory, exact native flow, both direction totals,
start/end ordering and zero loss are required. Workload source port is learned
from the unique captured flow; process/socket ownership is explicitly NOT_PROVEN.
The capture is capped at 120 seconds and two GiB; marker waits are five seconds,
offline export thirty seconds. Early exit, cancellation, deadline, truncation,
loss, source drift or malformed stop metadata leaves INVALID_PARTIAL evidence.
No timeout is extended to accept a failed experiment.

Output contains original pcapng/stderr, commands, tool versions, source SHA,
probe identities, readiness/stop records, UDP export, layer totals, failure or
result, and a SHA-256 inventory. Marker bytes are reconciled separately.
Successful status is PASS_DIAGNOSTIC_NATIVE_CAPTURE, not full B1 acceptance.
Keep performance observations diagnostic while capture is enabled. Physical
wire bytes, offload qualification, setup-versus-established phase splitting,
process ownership and the complete five-pair overhead analysis remain separate
gates. Docker veth runs establish mechanics only, never external NIC capacity.
