# Receiver monitor observation: local integration candidate

Correction to the earlier investigation: bounded.run already calls
finite_receiver.retain_owner(owner). That existing function permits exactly one
binding from the original receiver monitor thread, and cleanup checks use it.
The missing piece is a serialized observation reply for visualization, NOT a
missing retained owner. The existing binding must be reused, not replaced.

ObservedReceiverOwner extends the existing DrainingOwner implementation. Its
observe delegates once to the original method, then answers a pending in-memory
ObservationSlot using that observation. It performs no extra native observation,
file I/O, publisher call, socket operation or sleep. Terminal/draining, cancellation,
signal and reap revoke the slot. Viewer expiry revokes only visualization, not
the valid receiver. Native operations remain on the constructing monitor thread.
This is observed-owned-at-check, never a guarantee of liveness at atomic replace.

The receiver-only constructor is wired only in an inert bounded.run source
snapshot, NOT in the runtime launcher. No deployed runtime selection,
qualification gate or source pin changed. The old receiver binding
function was initially tested unchanged; the latest snapshot adds the lifecycle latch described below. Its source was extracted from finite_receiver.py
(source SHA b196ea52cabd526b1b912e08c33dd20ea1b057228607f2afba2b1d2846218609).
Tests exercise actual adapter/base owner methods with an injected OS backend and
one local thread; they do not establish native runtime qualification.

Next integration must select this adapter only for live-lab/receiver-command in a
fresh reviewed successor, pass through existing retain_owner, and bind authenticated
request/readiness pins. Original monitor thread remains the only reaper/signaler;
the control-plane never gets handles. Tests must then exercise actual bounded.run
and receiver stop/abort paths, including failure cleanup and generation invalidity.

Logging remains unresolved operationally. Read-only deployment inspection confirms
uncapped redirected handles. Without changing the running service, size monitoring
can reject new attachment but cannot guarantee a hard log cap. Rename/truncate/ACL
changes are neither safe evidence preservation nor reliable handle limits. A bounded
sink on a separately approved same8765 service restart remains the recommended
strict-cap option. No restart, deploy change, log write or manifest write occurred.

The named auxiliary1MiB donor and384KiB proposal are not an allocation; concurrent
logs and remaining auxiliary writers still need reconciliation. Native fixture07
proved only reader receipts. Publisher claims, actual receiver owner integration,
SQLite accounting, POST composition and campaign admission remain open.


## Isolated wrapper wiring

`receiver_bounded_run.py.snapshot` extracts unchanged `_command_path`, `_anchor`,
`_contain_retained` and `run` from bounded.py SHA
5417eb5fcd7db070aa077bd74e01f7dcb8084a6d1c967143a8dbbcfece3b0aff.
The only run changes are optional receiver_observation, strict receiver-path/type
validation before ClaimBook, receiver-only ObservedReceiverOwner selection, and
revocation if the existing retain_owner binding rejects. Default selection is
unchanged. Construction allocates no native handles; retain_owner still happens
before supervisor startup. No second binding, ready file, identity proof or
publisher permission is manufactured from the supplied slot.

Tests execute that complete run body and genuine containment/finally/history
control flow with injected admission, request validation, accounting, supervisor
and OS backend. They write small temporary JSON histories. They do NOT prove
real argv admission, accounting enforcement, actual watchdog composition,
receiver worker shutdown, native handles or runtime readiness. They exercise
no-slot compatibility, rejection before claims, binding failure before startup,
start/observe failures, retained cleanup and a successful observe/reap path.
Additional owner tests assert revocation inside backend/cancel/close callbacks,
not merely after their side effects. No services or successor files are changed.

Before activation, the selected constructor must be pinned into a fresh real
successor, receive the original receiver owner's authenticated slot, and pass
full watchdog/receiver cleanup and current accounting admission. This source-only
snapshot deliberately grants none of those conditions.

## Identity consistency is not readiness authentication

`ObservationSlot.bind_receiver` is a lock-protected one-use consistency primitive:
independently supplied identity, original anchor and115s deadline must exactly
match; prior observation use, rebind, mismatch or uncertain time revokes forever.
This method is exercised test-locally and is deliberately NOT called by the
prestart bounded snapshot. Existing no-binding sketch usage remains compatible.

The real bounded.run creates request.json before starting the worker, but
ready.json is produced only after startup. Therefore the current combined
run/request/readiness slot cannot be authenticated as a prestart proof. A future
integration must independently pin the generated request and actual readiness,
then expose observation on the retained original owner. Supplying a tuple from
the same caller or hashing expected readiness is not that authentication. No
ready file is fabricated, no claim that this primitive closes that runtime gate.

## Concrete remaining post-start integration seam

Read-only source inspection of finite_receiver.py at SHA
b196ea52cabd526b1b912e08c33dd20ea1b057228607f2afba2b1d2846218609
establishes this order:

1. Owner.start claims _CURRENT and starts its original monitor thread.
2. _monitor calls bounded.run; that function publishes request.json, constructs
   the native owner, calls retain_owner, and then enters supervise/start.
3. The worker eventually publishes ready.json. Owner.start reads it via _read,
   checks deadline/port and returns. This is the earliest existing readiness seam.
4. Owner.finish publishes stop, joins that same monitor, and checks exact retained
   owner cleanup plus ended.json. abort publishes the existing cancel marker.

_read checks regular single-link non-reparse file identity before/open/after and
bounds bytes, but returns only a decoded mapping. It does not retain the bytes or
file seal for later comparison, authenticate exclusive writer ownership, reject
all duplicate JSON keys, or bind request to independently retained source bytes.
A hash of whatever is found on disk is not independent writer authentication.

The current wrapper optional slot is chosen BEFORE step3, while the slot identity
requires readiness. Therefore neither fabricated expected readiness nor a second
owner instance is an acceptable connection. The next actual change must provide:

- A post-ready handoff from Owner.start to the original retained monitor owner,
  with no native handle operations on the control-plane thread.
- Bounded strict decoding and retention/revalidation of exact request+ready bytes,
  canonical parent identities and independently verified source/writer ownership.
  Reuse existing request/ready allocations; reading adds no permission to publish.
- Fail-closed observation disabled until that handoff completes; all failed
  imports/origin checks, admission, startup, reads, binding, stop and abort must
  leave it disabled/revoked. Original receiver175s and viewer115s stay unchanged.
- Serialization with existing monitor termination/reap, without holding its lock
  over filesystem I/O. A later exit disconnects visualization, never retroactively
  manufactures a valid live owner at publication time.
- Composed tests of actual monitor/start/finish paths, read mutation/replacement,
  late readiness, cancellation and late owner exit; then separate native evidence.

These are missing integration and evidence, not a request to weaken guards. The
current source-only consistency primitive cannot provide the post-start handoff.
No additional runtime setter, placeholder identity or file-authentication policy
was silently introduced. Existing qualification denial remains appropriate.


## Integrated post-ready snapshot (latest local revision)

The earlier missing-seam diagnosis above is now addressed in an inert
`receiver_owner.py.snapshot`, extracted from the same finite_receiver source.
Its monitor requests receiver_observation_enabled=True in the bounded snapshot;
the retained ObservedReceiverOwner starts with observation=None. The existing
ready branch calls PostReady only after readiness is read. The original owner
is reused; no native handle operation moves to the control-plane thread.

PostReady reads exact request8KiB/ready1KiB caps, rejects unsafe parent/file aliases
and replacement during reads, uses strict duplicate/nonfinite JSON decoding,
checks existing attachment_arguments, original owner argv/deadline, and retains
file identity plus raw SHA256. It rereads before and after one-shot installation.
The supplied root/source authority and exclusive writer identity are STILL
external qualification gates: seals authenticate neither the writer nor source.
`verify` must be used again before future publication; there is no publisher here.

Installation, terminal/cancel/reap disabling and generation checks share a short
in-memory lock. No native call or filesystem I/O occurs while holding it. A slot
installed during an existing native sample cannot answer until a subsequent
sample. A terminal state reached while no slot exists still permanently rejects
installation. Only a freshly bound slot can be installed, once; the old optional
prebound constructor remains source-sketch compatibility, not the new flow.

The actual start/finish/abort method bodies are exercised with injected thread,
qualification/admission and IPC wrappers, actual temporary request/ready bytes,
actual post-ready reader and injected OS backend. Finish/abort revoke before
existing stop/cancel work. Visualization failure is recorded separately without
stopping a valid receiver. In particular readiness between anchor+115 and+170
may satisfy receiver readiness but cannot attach the viewer or renew its115s
window. All real qualification denials/deployment files remain unchanged.

This fills the source-level post-ready path; it does NOT establish a real worker,
actual native monitor thread, whole accounting, source/writer authentication,
SQLite shutdown, log reservation, publisher authorization or campaign validity.


### Pre-binding stop race correction

The lifecycle now has a visualization-revoked latch independent of whether its
native owner has been retained. Its short viewer_lock serializes retain_owner,
post-ready install and revocation, with no file or native operation under it.
Abort/finish set this latch before stop/cancel work. Later retain_owner propagates
revocation to the newly bound owner; start/import/monitor failures also revoke.
PostReady uses this lifecycle installer instead of installing directly in the
start path. The original monitor-thread and exactly-once owner binding checks
remain. Installation failure permanently disables old and supplied slots and
cannot be retried into success. Post-install verification checks the owner still
has that exact active observation slot.

Regressions reproduce abort and finish before retain_owner, plus abort between
readiness verification and install. A pending cancel can no longer be followed
by a usable observation before the supervisor notices cancellation. These tests
remain isolated injected-thread/backend proofs, not native execution evidence.
