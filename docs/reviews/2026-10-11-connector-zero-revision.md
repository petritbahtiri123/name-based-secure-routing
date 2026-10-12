# Stage 3 bounded correction: positive authority revision

The ten-stage plan remains at stages 1â€“2 complete (2/10); Stage 3 is partial.
Stage 1 has the approved contract and Go/Rust ownership seam. Stage 2 has the
offline configuration gate. Development coordinators, isolated TLS loopback,
signed-authority fixtures, timer fixtures and CI invocation wiring exist, but
do not establish runtime authority/revocation delivery or close Stage 3.
Stages 4â€“10 have no new acceptance evidence from this task.

Chosen gap: Rust's test-only gateway compares receipt revision with its injected
snapshot but omits the positive-revision check used by the Python offline oracle
and signed fixture verifier. An agreeing zero/zero pair can issue a challenge.
The bounded change rejects that invalid receipt before challenge creation.
Registration and renewal regressions must preserve owner state and demonstrate
that failed cleanup still retains ownership until explicit confirmation.

Ruling: use the existing dirty checkout and scoped evidence ledger, preserving
all previous work; no commit, new worktree or broad branch audit. This follows
the explicit task scope. No live provider, wire allocation or policy decision
is introduced. Local cached offline checks only; no network trial is needed.

## Verified outcome

Both deterministic regressions failed before the one-line fix because Rust
returned a challenge for revision zero. Both pass afterward. Final neighboring
scope: **25 passed, zero failed, one ignored** (24 registration/cleanup tests,
one codec test; live loopback ignored). Scoped Clippy with warnings denied and
cargo fmt pass. Independent review found no blocking findings and confirmed
the proof path inherits the positive challenge revision and rechecks the current
snapshot before commit. Reviewer did not rerun tests.

Five supervised runs are retained, including the two-case red failure. Rust
1.97.1/edition 2024 used the verified existing target with locked/offline
dependencies and two jobs. No resource abort; all direct children reaped.
Starting free disk exceeded 11 GiB, end RAM exceeded 3.8 GiB, longest run 10.45s.
No new sockets, test PKI, containers, dependency downloads or credentials.
The existing default CI Rust profile already selects these exact targets.
Hosted CI and the live loopback were not run for this correction. Previous
live results and source/binary hashes remain historical, not current-live proof.

The stage table now reflects the existing real isolated TLS loopback while
retaining Stage 3's real authority/revocation/timer gates. Stages 4–10 remain
unaccepted; no readiness or production claim. No material new design decision
was needed for this parity correction. A real verified event producer still
requires approved receipt packaging/threshold integration; this task does not
resolve that gate. All earlier local changes are preserved, unstaged and
uncommitted on codex/nbsr-v3-wp0-wp1 at c7abbc4423a9ad05cea9cdf6678c231a34cafd59.
No push, hosted dispatch, security-setting or registry change occurred.

The adjacent JSON retains exact commands, source preimages/final snapshots,
incremental patch, current test-binary hashes and resource outcomes. Existing
AGENTS guidance was updated only for the positive-revision invariant.

