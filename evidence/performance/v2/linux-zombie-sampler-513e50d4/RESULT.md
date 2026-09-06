# Linux Docker compatibility smoke: FAIL, sampler lifecycle defect

Exact committed source: 6227fd86023d89107684dfc5ba9a4f0674dd72fa. Build passed with the unchanged pinned Rust/Python bases, locked Cargo and hash-pinned Python dependencies. Image: sha256:fdb5ff4f1795450f562ae4ae2aa2dbbfda7d6601e11ab9b8cc452f265b1613a3.

The restricted nonroot/read-only/network-none/cap-drop container exited 1. The first Direct workload produced its valid 20-second terminal record (1,921,256 completed operations, zero errors), but the Python sampler failed at linux_loopback.py:130 reading /proc/55/fd. Consequently the runner correctly reports FAIL, zero valid runs; no NBSR cell or complete matched matrix was reached. The Direct binary terminal record is diagnostic evidence only, not accepted performance evidence.

A separate container with identical UID/security restrictions reproduced this lifecycle boundary: live child state R had three readable FDs; unreaped child state Z returned PermissionError errno13 for fd enumeration, and child exit code was0. This proves a final-state sampler defect, not persistent inability to sample live processes. The existing observe() intends to collect zombie final CPU before wait/reaping, but sample_process enumerates FDs first.

Smallest proposed repair: preserve final stat/start-tick/CPU and exit-code validation, represent terminal FD count as unavailable (not invented zero), and handle an exit race only after re-reading stat proves the same PID/start_ticks is Z. A PermissionError while the same process remains live must still fail. Add a literal zombie/exit-race regression before changing the runner. No repository repair was made here.

The original smoke, volume, and probe container remain stopped and retained, labelled nbsr.smoke.run=nbsr-linux-smoke-6227fd86. No Docker privileges, timeouts, authentication, protocols, or workload limits were changed. Initial C free35.15GB; final about21.47GiB. Recipe files, source bundle, toolchain/package manifests, raw logs, probe and container inspection are indexed; bundle-checkout is an exact-commit preparation copy and excluded from this redundant index.

Scope: Docker Desktop Linux VM compatibility attempt only. No hardware/core ceiling, bare-metal server, or successful Linux suite claim follows. Timed slot is clear.
