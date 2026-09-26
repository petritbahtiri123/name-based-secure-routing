# Administrator-only final validation

## September 26 final attempt — do not repeat current WPR campaign

Status: **PLATFORM_DIAGNOSTIC_LIMIT / INVALID_PARTIAL**. The updated
`CPU.light` campaign at `083c0182` also failed its first captured-cell stop
with `0x80071069`, profile `CPU.Light.File`. Retained root:
`C:/NBSR-build/b5-direct-cpu-20260926-205215-2fbd44b2`.
WPR subsequently reports not recording and no benchmark peer remains active.
The standalone light preflight passing does not qualify capture during this
benchmark. No sole cause, hardware ceiling or NBSR defect has been established.

**The command below is historical and must not be repeatedly rerun.** No further
user-run WPR command is pending. Preserve all verbose/light attempts, stop logs,
binary/source metadata and checksum indexes. Missing ETL means causal profiling
and matched observer qualification remain incomplete. Further elevated capture
requires a genuinely new measured question and method, not another profile
guess. Continue independent non-admin work; do not substitute these diagnostic
cells for a qualified near-ceiling soak.

## September 26 update — current command preparation

The same command/path below now points to a clean feature-branch checkout at
`083c0182c2bdcfa030e3c0a6a239977f3cae0cf5`. The folder suffix `4eb62c09`
is historical; the earlier source description below describes the previous
failed attempts, not this new run. Release preparation rebuilds current source.
Do not pool previous/current source results or label them matched pairs.

The wrapper now uses `CPU.light` and runs xperf header validation after each
captured cell. Unreadable traces, missing/ambiguous loss totals or nonzero lost
events/buffers stop the campaign with all artifacts retained. Five off/on pairs,
fixed workload, deadlines and the 5% observer-impact gate remain unchanged.
CPU.light has no call-stack attribution: only supported CPU/scheduling analysis
may follow. The 120-second synthetic light preflight exported successfully with
zero lost events/buffers; matched benchmark observer qualification is NOT_RUN.
Earlier verbose preflight lost 46,258 events; two full verbose attempts failed
WPR stop with 0x80071069. Neither failure is discarded or claimed repaired.
Focused regression tests (six), Ruff, PowerShell syntax and real zero-loss header
validation pass. Actual elevated end-to-end execution remains user-run.

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
pwsh -NoProfile -ExecutionPolicy Bypass -File "C:\NBSR-build\admin-validation-source-4eb62c09\scripts\capture_b5_direct_cpu.ps1"
```

The prepared source is an independent clean local clone at
`4eb62c093273dcfe883c0bb5c02cf69dbd426c20`, on the expected feature branch.
The original OneDrive checkout contains three pre-existing untracked evidence
variants with different byte hashes; they remain untouched. The clone avoids
weakening the clean-source gate or deleting those files. Its capture script
matches the committed bytes exactly; checkout line-ending normalization and
index refresh changed no source content or history. Keep this clone at its
prepared path and do not update it while capturing. This diagnostic is bound to
that recorded source, not automatically to later documentation commits.

The script requires the expected clean feature branch, refuses an existing/unknown WPR session, prepares release binaries, and runs five counterbalanced off/CPU pairs at the fixed historical diagnostic rate (120seconds per cell, roughly20minutes of workload plus setup/export). No current-ceiling or stable-capacity claim is made. It retains every failed cell and stops without replacement, stops only the recording it successfully started, and hashes raw outputs in a fresh `C:\NBSR-build\b5-direct-cpu-*` root. At least5GiB free is required before each capture; it deletes nothing. Do not run other captures or workloads concurrently.

Expected output: `CAPTURE_READY: ...`, ten completed diagnostic cell folders, five ETLs, commands/environment/telemetry, logs, and a SHA-256 index. Failure instead produces retained partial evidence and an explicit error. Return the output root after execution; do not delete failed attempts.

Acceptance after return: verify source/binary/workload matching and all hashes; compare five-repeat median goodput and median steady-window p99 between observer arms against the5% absolute-impact gate, with both CVs reported. Reject causal attribution if distorted or incomplete. If accepted, restrict stack/time analysis to each owned peer PID and its measured window; separate runtime, QUIC, socket waits and benchmark work. Raw ETL stays local because it may include unrelated system-process metadata. No automatic optimization follows from mere correlation.

Validation performed here: PowerShell parser PASS; non-admin refusal PASS. Elevated end-to-end execution remains NOT_RUN. This is a deferred diagnostic, not a mandatory repeat of the earlier rejected handshake traces.
