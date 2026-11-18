# Source-only observation slot and log-control options

ObservationSlot sketches the reviewed one-slot, sequence/generation contract. It
does not spawn a thread, read a file, inspect a native handle, publish a manifest
or grant authorization. The native monitor is the sole intended answerer; that
caller identity is not enforced by this in-memory class. Runtime integration must
bind it to the actual original supervisor and authenticated immutable identities.

The control-plane requests, polls pending status, takes exactly one reply and
revalidates immediately before its separate I/O. Missing replies, stale sequences,
revocation, nonfinite/backward clocks and deadline expiry permanently fail the
attempt. All locks protect only tiny in-memory state; no callback or I/O runs
under them. A test deliberately blocks publication while monitor revocation still
proceeds. A valid check only proves observed-owned-at-check. The child may exit
afterward; this is not an atomic-liveness guarantee. The caller remains responsible
for one publication attempt, bounded waiting, cancellation and observed disconnect.

This model is not integrated into the native supervisor. Tests use the model and
one bounded local thread, not a VM, receiver or benchmark. CI selects the file.
It does not replace file pins, live owner binding, output claims or qualification.

## Existing viewer log options: evaluation only

Current service was launched with stdout/stderr redirected by Start-Process into
stable-restored.stdout.log/stable-restored.stderr.log. No access log is enabled;
this does not bound exception output. Existing retained source/data totals288086B.
No live service or file was changed during evaluation.

1. **No-restart observation/abort guard.** Sample current log sizes/identities and
   include growth in resource admission. Abort the new attachment attempt before
   its own writes if the reservation is exhausted. Lowest operational impact, but
   detection is after a write and cannot hard-cap an independently running service.
   This is useful additional monitoring, not a solution to a strict peak guarantee.
2. **No-restart rotate, rename, truncate or permission change.** Not recommended.
   Existing redirected handles may keep writing to the old file, renaming can fail
   on Windows sharing rules, truncation loses retained evidence, and permission
   changes do not reliably constrain already-open handles. None proves a cap.
3. **Controlled same8765 service restart with a bounded logging sink.** The most
   direct route to an enforceable writer budget. Preserve existing logs and viewer
   data; identity-verify the service, prepare rollback, and account fixed log slots
   plus dropped-log diagnostics explicitly. This requires separate approval and
   review because it briefly affects the existing viewer. No such restart or sink
   has been implemented. A fixed rotation size alone does not bound a single huge
   log record; the sink must cap encoded records as well as cumulative storage.
4. **Treat existing service logging as independent external activity.** Possible
   only as an explicit accounting-policy decision, never silently exclude it. It
   changes what the resource guarantee covers and therefore is not a technical fix.

Recommendation: retain no-restart monitoring for information, but do not call the
384KiB proposal enforced. Prefer a reviewed bounded-sink change during a separately
approved same8765 maintenance window if a strict whole-directory bound is needed.
The donor remains the named1MiB auxiliary partition, subject to a full inventory of
its other writers. No new allocation or deadline extension was made here.

Native fixture07 still proves only reader receipts. Full supervisor integration,
receiver/SQLite accounting, publisher claims, source/owner pins and POST composition
remain required for an admitted benchmark. No full repository or native run was
performed for this sketch; only bounded selected lifecycle tests and focused lint.
