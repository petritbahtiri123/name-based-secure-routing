# Local-only two-stream prerequisites snapshot

This snapshot retains baseline ad77d59754651fee449bb1d9c14a946f9f3b2d15 and selects
only the reviewed finite/lifecycle cleanup, local watchdog, exact-ID disposal,
Windows management/Job backend and Docker provisioning overlays. Rust source,
Cargo manifests/lockfiles and historical fixtures remain baseline bytes. Unrelated
KAR, recovery, CI and broader status changes are excluded. Raw local evidence,
machine inventories, credentials and build outputs are not added to this commit.

Existing committed historical evidence remains in the baseline tree; the local
checkout is sparse for evidence/, artifacts/ and demo-video/. Sparse materialization
does not weaken a validator: a required missing artifact remains a blocker.

Run the affected Python performance tests for post-close, cleanup failures,
finite/lifecycle run, watchdog, local-container disposal/sequence and Windows
management/Job/provisioning. Use the provisioned environment, no-cache mode and a
fresh test-owned temporary root on Windows. Baseline Rust benchmark code needs no
source change. A later build still requires verified Linux cached dependencies,
locked offline release commands, max2 jobs and the approved resource/time guards.

WindowsOwner assigns suspended processes before resume and retains exact handles.
DockerCommand bounds host CLI jobs; daemon effects require separate exact-ID
inspection. DockerProvisioner selects one internal network, exact readonly role
mounts, bounded non-root endpoints and fresh absence confirmation. Unknown creation
blocks replacement; known failed creations remain cleanup-addressable. No socket
is delegated. The existing Sequence/WindowsWorkload use normal, expected interrupted
INVALID_PARTIAL and fresh cells. Local worker exit never proves endpoint disposal.

The Docker command supervisor retains primary and cleanup failures separately,
including the failing stage and available OS error details. Timeout remains failure
even when cleanup succeeds; retained handles stay visible when cleanup fails. The
historical timed-out cache probe remains UNCONFIRMED and is not reclassified by
this diagnostic fix.

The baseline stored 87 CRLF blobs under LF text attributes. Explicit per-path
-text exceptions in .gitattributes preserve their raw bytes and blob identities
without renormalization or hidden local attribute overrides. Existing sparse
exclusions are unrelated to these exceptions. A normal checkout must remain clean
using the tracked attributes. Byte inventories are retained outside the commit.

This commit does not authorize TLS generation/access/copy/mount, QUIC traffic,
downloads, live deployment or publication. Credential setup remains a separate
user-controlled handoff. Source, native containment, runtime/cache and actual
transport results must be reported separately; no production/SPHERE/capacity claim.

## Offline observation-race correction

The Win32 backend samples Job membership before the leader handle. These reads
are not atomic: leader-first sampling could observe a live leader, then an empty
Job after termination, incorrectly classifying an ordinary exit as inconsistent.
Job-first sampling conservatively retains a stale positive count until another
poll. Reaping still requires an exited leader and an empty Job; deadlines and
invalid-observation rejection are unchanged. The fake-kernel regression is
`test_exit_between_native_observations_retains_until_next_poll`.

This correction does not explain the six-second Docker creation timeouts.
Historical attempts and cleanup uncertainty remain unchanged. A subsequently
approved create-only diagnostic still observed an empty Job with an unsignalled
leader after termination, despite Job-first sampling. The ordering regression
passes but is insufficient to resolve that live condition. CLI launch completed
promptly; its subsequent wait reached the work cutoff. Daemon receipt and internal
delay remain unknown. Any further live diagnosis requires fresh approval.

Command diagnostics retain at most 128 timestamped events (initial 32 and recent
96), suppress repeated identical observations, and count dropped events and
diagnostic failures. Host records cover create/assign/resume, changed process/Job
observations, terminate and close; worker records cover CLI launch/PID, wait and
reply. Ordinary diagnostic errors cannot interrupt handle transfer or cleanup.
These file writes can stall and are not an unconditional real-time guarantee;
missing/truncated diagnostics never prove cleanup or daemon cancellation.

## Asynchronous termination: pending ownership

The separately authorized process-only diagnostic observed the same verified
helper PID with an empty Job and unsignalled process immediately after termination,
then a signalled process and empty Job about 21ms later. The owner now treats that
first pair as pending, retaining all exact handles and polling within the caller's
existing deadline. It never substitutes a native process count or infers completion
from an empty Job. Reaping rechecks both proofs; query errors and failed closes
still retain ownership. A persistent unsignalled process exhausts the original
cleanup deadline. A work timeout remains a failure even if cleanup later succeeds.

Production ownership uses the retained CreateProcess handle rather than reopening
by numeric PID; no PID-mismatch fallback is introduced. Tests assert identical
Job/process handles across observations and keep later descendant activity blocking.
This offline fix has not been exercised live; prior UNCONFIRMED records and the
unexplained Docker creation delay remain unchanged.

An explicitly approved cold-start diagnostic may construct DockerCommand with
max_timeout=32 and call create with timeout=32:30s work plus2s helper cleanup.
The default remains8s (6s work); other commands in that trial retain8s, and the
overall cleanup-inclusive deadline remains120s. This is an opt-in trial budget,
not a latency guarantee or performance pass. Cached inspections do not establish
engine readiness. No resource-saving or other persistent setting changes follow.

Windows Docker command preparation checks the actual Popen serialization before launch,
with a conservative 30,000 UTF-16-unit ceiling including NUL. Worker launch errors
retain their original type/message/errno/winerror in the request-bound reply; existing
timeout and cleanup supervision remain independent. The offline rust_cache_metadata
probe reads only the approved Cargo.lock file mount, with no additional script mount.
Its package/archive observations do not establish offline build readiness.

An explicitly approved metadata-only trial may use CellBudget(work_seconds=240,
total_seconds=300) and DockerCommand(max_timeout=122, trial_budget=budget).
Both must use the same monotonic clock. Each command is capped by the original
trial deadline; 62s creation and 122s metadata waits include 2s helper cleanup,
leaving at most 60s and 120s of work respectively. Extended budgets reserve at
least 60s for cleanup; defaults remain 95/120s and an 8s command ceiling.
Resource checks apply during work, never as a prerequisite to owned cleanup.
These limits require task-specific authorization and do not authorize builds,
downloads, retries or broader mounts. Metadata resolution is not compilation.
