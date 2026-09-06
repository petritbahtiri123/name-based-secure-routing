# Administrator-only final validation

Campaign ledger â€” **IN PROGRESS**, not a final validation or funding freeze.

No additional Administrator command is currently required to analyze the retained Task 4l/4m captures. The user-supplied captures have been ingested; their raw artifacts and observer failures are preserved. Do not repeat them merely to obtain a favorable result.

Residual handshake attribution is **PLATFORM_DIAGNOSTIC_LIMIT**: full ETW, filtered AFD and lightweight accept-pump timing did not satisfy the matched observer gates. A further elevated trace is not a required closure step unless a new, specific unanswered question and a less-distorting capture method justify it. No production or hardware ceiling follows from this limitation.

Scoped packet accounting and Docker private-origin isolation have completed without an additional elevated command. Remaining final validation is still in progress. Add an elevated command below only after proving that the actual validation cannot run in the current non-elevated environment. Each entry must include one exact command, why elevation is needed, expected output, retained evidence location and acceptance checks. No security-policy or firewall changes are authorized by this ledger.

## Required commands

### 1. ADMIN_REQUIRED: matched Direct paced CPU attribution

Measured question: at source2d7525f3, the one-core32-stream1KiB Direct ten-minute cell achieved only20.17% of its unchanged offered rate (0.114662 Gbit/s), with high latency already in the first30-second window. A separate NBSR cell achieved97.68%. The Direct cause is UNRESOLVED; no production/hardware attribution is justified.

The current non-elevated process was verified unable to start `wpr -start CPU -filemode`: exit1, error0xc5585011, failed to enable system-performance profiling. `wpr -status` first reported no active recording. No existing session was cancelled and no security policy was modified. The wrapper's own elevation preflight also rejects this process before creating a capture directory.

After other meaningful non-admin work is exhausted, execute this **one command** in Administrator PowerShell from an otherwise idle host:

```powershell
pwsh -NoProfile -ExecutionPolicy Bypass -File "C:\Users\bajra\OneDrive\Documents\NBSR\scripts\capture_b5_direct_cpu.ps1"
```

The script requires the expected clean feature branch, refuses an existing/unknown WPR session, prepares release binaries, and runs five counterbalanced off/CPU pairs at the fixed historical diagnostic rate (120seconds per cell, roughly20minutes of workload plus setup/export). No current-ceiling or stable-capacity claim is made. It retains every failed cell and stops without replacement, stops only the recording it successfully started, and hashes raw outputs in a fresh `C:\NBSR-build\b5-direct-cpu-*` root. At least5GiB free is required before each capture; it deletes nothing. Do not run other captures or workloads concurrently.

Expected output: `CAPTURE_READY: ...`, ten completed diagnostic cell folders, five ETLs, commands/environment/telemetry, logs, and a SHA-256 index. Failure instead produces retained partial evidence and an explicit error. Return the output root after execution; do not delete failed attempts.

Acceptance after return: verify source/binary/workload matching and all hashes; compare five-repeat median goodput and median steady-window p99 between observer arms against the5% absolute-impact gate, with both CVs reported. Reject causal attribution if distorted or incomplete. If accepted, restrict stack/time analysis to each owned peer PID and its measured window; separate runtime, QUIC, socket waits and benchmark work. Raw ETL stays local because it may include unrelated system-process metadata. No automatic optimization follows from mere correlation.

Validation performed here: PowerShell parser PASS; non-admin refusal PASS. Elevated end-to-end execution remains NOT_RUN. This is a deferred diagnostic, not a mandatory repeat of the earlier rejected handshake traces.
