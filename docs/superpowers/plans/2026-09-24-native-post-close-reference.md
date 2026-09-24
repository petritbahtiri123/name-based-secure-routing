# Native post-close reference prerequisites

The native finite coordinator currently proves process joins, not runtime-owned
resource cleanup. A paced reference must not be accepted using process exit alone.
Reuse the existing eleven-counter `post_close_cleanup.validate_report` contract.

Add an explicit optional post-close-report mode to native finite peers and the
coordinator. Defaults preserve accepted evidence. For NBSR append only the existing
benchmark cleanup-report flag to both peers, bind report role/PID to the owned
child, require all eleven zero counters before PASS, and independently revalidate
transferred evidence. Direct retains its process-exit scope; never fabricate
NBSR resource counters for Direct. Requested mode must match both peer metadata,
executed arguments and coordinator configuration. Observer cost remains unqualified.

RED: missing report, nonzero ownership, wrong PID, bool/noncanonical mode, requested
but omitted flags, asymmetric mode and resealed report corruption fail. GREEN:
valid source/destination reports pass; default historical fixtures still pass.
Focused tests and one review, then atomic commit and exact-source real validation.
No production/wire/security/ACK/timeout changes. This closes only the native
reference cleanup prerequisite; paced drift/resource classification remains open.
