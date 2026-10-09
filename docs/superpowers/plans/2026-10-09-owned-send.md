# Explicit Owned Send Implementation Plan

**Goal:** Add explicit bounded owned send pause/resume/abort without changing existing caller intent.

**Architecture:** A non-Clone operation exclusively borrows its stream and owns immutable payload progress. A weak registration allows revocation cleanup without a background task; FIN occurs only at full completion.

**Tech Stack:** Rust 2024, cached Quinn/Tokio, existing transport errors and byte quotas.

**Spec:** `docs/superpowers/specs/2026-10-09-owned-send-design.md`

## Global Constraints

- No wire changes, background sender, downloads, or blanket Drop reset.
- Publication was subsequently approved for this verified six-file package only,
  on `codex/nbsr-v3-wp0-wp1`; further analysis does not authorize another patch.
- Keep 1,048,576 stream payload / 8,388,608 bidirectional channel byte limits.
- Offline, at most two jobs; existing 95-second work cutoff and disk/RAM guards.
- Preserve the 64/4096 legacy diagnostic and unrelated files.

## Review Focus

- Revocation while drive owns the async lock must clear paused ownership without repolling.
- Completion versus revocation must not reintroduce a released quota reservation.
- Cancellation before/after one accepted chunk must neither duplicate nor lose bytes.
- Existing application writes must not be mixed with a new owned operation.
- Completed owner Drop must preserve normal FIN; unfinished owner Drop must reset.

### Stage 1: owned operation and focused evidence

**Files:** add `crates/nbsr-transport/src/owned_send.rs`; modify `quinn_adapter.rs`,
`lib.rs`, and `control_read_tests.rs`; add the spec and this plan.

**Interfaces:** begin_owned_send(&mut self, Vec<u8>) -> Result<OwnedSendOperation<'_>, TransportError>;
OwnedSendOperation::drive(&mut self) -> async Result<(), TransportError>; abort(self).

- [x] Write tiny-window loopback tests for exact repeated resume, abort/drop, quota,
  revocation, bounds and rejected legacy mixing. Preserve separate legacy red evidence.
- [x] Run the owned-send regression before implementation and record the missing API failure.
- [x] Implement only the operation, weak cleanup registration, and legacy-write marker
  needed to reject mixing. Reuse cancel-safe writes and existing errors/quotas.
- [x] Run focused owned-send and neighboring payload/ACK tests; all owned tests must
  pass. Report the unmodified legacy red diagnostic explicitly, not as a new regression.
- [x] Independently review exact diff; fix in-scope findings and verify formatting,
  whitespace, and all-target Clippy with the resource guard.
- [x] Report stage 1 and remaining stages without committing or pushing.

### Stage 2: borrowed abandonment guard (approved bounded follow-up)

- [x] Inspect borrowed-send timeout callers and the retained 64/4096 regression.
- [x] Specify zero-progress cancellation versus terminal partial cancellation.
- [x] Add focused regressions and observe failures before the minimal guard.
- [x] Preserve the owned API and normal/empty FIN; no caller/deadline migration.
- [x] Address the independent review's zero-progress revoke/drop gap with a red test.
- [x] Complete final exact-diff review and bounded library/integration checks.
- [x] Complete final lint/format/whitespace checks (all passed).
- [x] Record all current pass/fail counts; no commit or push.

### Stage 3: echo response cleanup (approved local follow-up)

- [x] Read the current echo abandonment contract and reproduce clean 64/4096 EOF.
- [x] Add zero-progress response cancellation/revocation and quota-failure regressions;
  observe the missing terminal transitions before implementation.
- [x] Arm the existing scoped guard after complete receive-state transfer, preserving
  resumable reception and successful FIN/quota behavior.
- [x] Add peer STOP_SENDING and empty-response controls; preserve original assertions.
- [x] Independently review the exact production diff.
- [x] Finish bounded library and relevant integration/demo checks.
- [x] Finish final lint/format/whitespace checks (all passed).
- [x] Record all run outcomes and limitations. No commit or push.

### Later echo/composite resumption (not implemented)

Design phase-aware resume and rollback tests separately; keep response/request
identity and bidirectional quota ownership. Never reread an existing echo response
or resend a request after entering receive phase. Review before implementation.

## Historical stage-1 completion evidence

See the spec's full run table, including failed attempts and the retained legacy
failure. Final scoped library: 90 passed / 1 legacy failure / 1 pre-existing ignored
soak; stream-credit integration: 11 passed; owned-send subset: all 8 pass. Independent
review found no blocking issue; its deterministic ordering coverage suggestion and
pre-Drop cleanup assertion were implemented. All-target Clippy passed. No commit,
push, caller migration, settings change, download or benchmark occurred.


## Borrowed guard follow-up outcome

The original regression is now green without changes to its assertion. Current
library: 96 passed / 0 failed / 1 existing ignored soak, including eight owned-send
tests and five new borrowed-send tests. Relevant integration: application_stream
4, stream_credit_integration 11, drain 12, multi_stream 3, all passing. Full red/green
attempt counts and review evidence are preserved in the spec. No echo/composite
phase migration, caller rewrite, deadline extension, or publication occurred.


## Echo guard follow-up outcome

Original response-truncation reproduction now passes unchanged. Final library:
100 passed / 0 failed / 1 existing ignored soak. Relevant integration: 30 passed;
selected demo-backend controls: 3 passed. Earlier failing runs, including the
corrected STOP_SENDING test-control assumption, remain recorded in the spec.
Receive cancellation remains resumable; response cancellation after the completed
request handoff is terminal, including zero response progress. No response-resume
API, composite migration, or benchmark change is included. Publication of this
verified four-file follow-up was subsequently approved on the same branch.
