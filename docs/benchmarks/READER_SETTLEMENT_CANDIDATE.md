# Reader closure/settlement candidate (offline only)

RUN1709 completed its native20-second workload but failed actual calibration span107.488456282s >90s. Importing these opt-in modules starts no process and replaces no campaign launcher. Calling the promoted native owner can launch a real process as described below; no module grants benchmark authority or relaxes that gate.

`reader_settlement.py` separates OPEN, CLOSED_UNSETTLED and final lifecycle acceptance. Checkpoints can reap exact successful empty ownership during a long scan; only a clock-probe permit may follow closure. Full resource reconciliation is still required. Capture writes seal after final hash; all writes seal after settlement. Cancellation remains fatal after closure. Lifecycle acceptance explicitly does not establish campaign validity.

`BoundReaderOwner` binds an already-started retained job to immutable argv, deadline, run/source and request hash, detects handle replacement, and prevents double reap. The native owner remains available to the outer cleanup owner after failure. It does not start a process.

`reader_acquisition.py` separates transport closure from owner settlement. The final frame pump may finish while bookkeeping continues. Readiness failure and late reader/finalization latch invalidity. The trusted caller must invoke the early hook only after exact empty process-group proof and reaping, then validate final bytes. Invoke finish promptly within the original deadline, never defer it until after bookkeeping.

## CI coverage

The python-core profile explicitly executes the five reader test files on its existing Linux/Windows matrix. Tests cover state transitions, fail-closed late failures, one-use permits, retained handles, blocked descendants, source identity, original deadlines,90s boundary, output sealing and actual thread finalization. Offline tests are not a live-VM or Windows-native containment proof.

## Still required before successor workload

- Selected exact WindowsOwner/DrainingOwner/backend and fixed-purpose ClaimBook/writers are now promoted with source hashes in READER_OWNER_PROVENANCE.json. Full bounded wrapper, source chain, snapshot walker and live adapter remain task-local/unintegrated. Do not vendor the remaining private checkout blindly.
- Bridge the bound owner into the surrounding watchdog without a second observe/reap on consumed handles. Preserve all cancellation/termination paths and independent endpoint cleanup.
- Bind exact capture bytes and final parser validation, quiesce every writer, retain immutable run/source/request hashes in exclusively written bounded receipts.
- Map ALL normal, cleanup, receiver and metadata writes to existing per-purpose ClaimBook and aggregate reservation accounting, including historical bytes. Candidate capture/receipt partitions demonstrate state sealing, not a replacement for the entire campaign budget.
- Implement exact source-pinned, bounded, cancellable POST clock-probe argv. Generic callback inputs in this offline contract must never become arbitrary-command authority.
- Full accounting reconciliation must finish and pass before campaign acceptance. Preserve actual same-source <=90s calibration, all probe checks, hashes and independent cleanup. No cached mutable history or enlarged scientific bounds.
- Independently review the complete adapter simulation, then notify the user before any authorized fresh run. Continue using existing Performance Lab8765 only.

No live integration is enabled by importing these files. RUN1709 stays frozen, invalid and retained.


## Promoted owner and reservation primitives

`reader_windows_owner`, `reader_windows_backend`, `reader_windows_drain` preserve selected original class bodies (executable AST comparison, excluding docstring whitespace). The owner class is extracted without unrelated container or management executors. Coherent job accounting is refreshed after leader exit; descendants are not inferred absent. Provenance records exact source-file hashes because the retained collector directory is not a Git checkout. No commit ancestry is invented.

Imports are inert. HOWEVER, `WindowsOwner.start()` with the real backend launches a suspended Windows process, assigns its job, and resumes it. That is a real process action requiring the caller's explicit authority; this module is not a launcher permission. All tests here inject the backend; native containment is unproved. On start/assignment/resume/termination/partial-close failure the outer supervisor MUST retain and clean the exact owner. This candidate does not add an automatic cleanup owner. Do not discard the object when an exception escapes.

`reader_output_limits` promotes the original pure fixed-purpose ledger and bounded writer, preserving quotas, precharge, partial-write failure latching, one-use claims and state locks. `reader_phase_budget` extracts only original arithmetic project/align, not the filesystem scanner. Its historical150MiB/global defaults are not admission for another campaign. Existing bytes plus all remaining normal/cleanup/auxiliary obligations must be charged; per-slot validity alone is insufficient. The lifecycle's two-partition model has NOT yet been wired to the full ledger; the next adapter must preserve every original purpose, complete aggregate snapshot and exclusive output identity.

Review failures were reproduced before correction: late cancellation, writes after capture finality, writes after settlement, readiness timeout, late completion, and verification-exception restore. All are now latched invalid. Backend tests also cover assignment/resume failure, retained job when configuration AND close fail, partial close, exact unassigned termination routing, and unsuccessful termination retaining ownership.
