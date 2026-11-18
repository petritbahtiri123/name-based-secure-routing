# Existing Performance Lab attachment: offline binding

Read-only inspection found the existing 8765 listener owned by PID4176, Python
`-B -m uvicorn serve_stable:app --host 127.0.0.1 --port 8765 --no-access-log`.
Its command/creation identity matched the retained service receipt in the
2026-11-17 lab-stable-viewer deployment. Its active attachment still names the
expired RUN1709. No listener, active manifest, database or retained run was changed.

The existing route is owner_attachment.publish -> active-attachment.json ->
StableSession -> private finite receiver on 8766. Port 8766 is not a second
user dashboard. The publisher already refuses an expired original 115-second
viewer window; the receiver's 170/175-second envelope does not extend that window.

`reader_viewer_binding.attachment_arguments` binds already authenticated receiver
request/readiness objects to that publisher's existing arguments. It checks exact
successor worker argv/output, original trial anchor, 170/175 request deadlines,
absence of parent_end/cleanup_purpose, readiness run/port/deadline, and freshness.
The source contract is the successor bounded.py `_request_window` receiver branch
and request construction, plus finite_receiver.py ready publication. The native
owner's internal 173-second bound is NOT the request cleanup_deadline.

The unchanged existing publisher is retained as a test snapshot. A temporary-only
integration test passes the adapter output through that actual publisher and
verifies the existing four-field attachment format. CI selects the tests. This
does not authenticate raw files, start an observer, or prove campaign admission.

## Runtime work not yet connected

A separately supervised control-plane owner must read bounded, identity-pinned
request/ready files from the admitted fresh successor, recheck their bytes and
owner, call this adapter, then the existing deployed publisher. It must charge
lock/pending/manifest writes and retain its bounded result outside PRE/POST. It
must never renew the anchor or publish fixture07 as a benchmark. This caller,
its exclusive path ownership and writer allocation are still required; the pure
binding adapter is not a substitute for them. There is no automatic runtime call.

The finite receiver still requires native qualification, and actual bounded
wrapper/POST/receiver accounting composition remains incomplete. Publication must
show waiting/unqualified, not claim PASS from readiness or receipt completion.
No full repository suite or live dashboard integration was run for this change.
