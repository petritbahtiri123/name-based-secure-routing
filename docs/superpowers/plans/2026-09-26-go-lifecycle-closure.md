# Go lifecycle closure and outreach continuation

Budget baseline: weekly used 3%; user authorizes at most 17 additional points.
Stop with headroom before 20% account-wide usage; percentages are approximate.

Order: close measured Go lifecycle cleanup gaps; preserve scoped resource evidence;
attempt qualified soak only with a valid reference/observer; consolidate outreach.
No hardware/server results or live federation claims without execution.

Current finding: runLifecycle starts concurrent goroutines waiting unconditionally
on concurrentStart. Error paths before release return without joining those
workers or closing the dialed peer. Prove cancellation behavior with focused RED
tests; use per-connection cleanup scope, context cancellation and joined workers.
Preserve successful destination completion/ACK order and all wire/security gates.
This is independent benchmark peer lifecycle work, not a production speed claim
or proof that this caused previously observed successful-cycle memory growth.

Verification: focused Go regression, affected package race/vet, unchanged existing
completion tests, release peer + retained lifecycle before/after when available.
No counter may imply ownership of uninstrumented QUIC internals.

Docker is currently unavailable; use Windows validation first. WPR remains a
recorded platform diagnostic limit; do not request repeated elevated captures.
