# Catchable controller cancellation: measured orphan defects and fixes

Two independent live RED controls reproduced orphaned benchmark processes:
- Native finite destination at 1d24cb4c: SIGTERM killed the Python controller;
  the same QUIC peer PID/start identity remained sleeping with PPid 1, and the
  attempt had no sealed terminal result.
- Existing loopback runner at 9d36266f: SIGTERM killed the controller while both
  source and destination stayed alive with PPid 1. The incomplete attempt is
  retained under the native raw root's green/loopback-signal-baseline directory;
  its injection/identity observations are retained in the loopback raw root.

The owned diagnostic containers were stopped to clean those rejected baseline
orphans. These are harness reliability defects, not NBSR runtime ownership leaks
or production security defects. No failed attempt was relabelled as successful.

Native fix 9d36266f and shared-helper/loopback fix b5272672 defer SIGINT, SIGTERM
and SIGHUP requests until an explicit ownership safe point. A signal cannot throw
between Popen creating a process and the controller recording ownership. Repeated
catchable requests cannot interrupt finally cleanup. Each owned child is killed
and reaped; cancellation is rejected and retained, never counted as a valid cell.
The loopback runner now records forced-cleanup exits. SIGKILL/host failure remain
outside a Python handler's guarantee and require the owned service/container lifecycle.

LIVE GREEN: all three signals pass in each runner. Native peers are absent after
cleanup; loopback checks both peers' original PID/start identities are absent,
with exit -9 and zero accepted runs/ACKs. Native normal controls complete three
counterbalanced Direct/NBSR pairs (six cells); CV 4.241% / 2.982%. Loopback expands
to five pairs (ten valid cells) because CV exceeds 5%; residual CV 13.155% /
12.402% remains PARTIAL_DISPERSION. These are functional regression controls,
not strict-stable capacity, performance improvement or external hardware results.

Literal Python RED precedes each fix. Final focused suite: 72 PASS, including
post-spawn cancellation before either peer can escape registration, reaping,
ACK ordering, pair provenance, network inventory and existing terminal sampling.
Ruff/diff checks pass. Fresh locked release builds at both fix SHAs reproduce
exactly the previously retained three binary hashes: Rust production/benchmark
workload binaries did not change. No protocol, wire, security, authority, timeout,
acceptance threshold or workload was weakened. No performance rerun was discarded.

The common cancellation helper is currently wired to native finite and loopback
CLIs only. Do not extrapolate these guarantees to other campaign controllers.
Packet-collector cancellation is a separate pending investigation at this stage.
