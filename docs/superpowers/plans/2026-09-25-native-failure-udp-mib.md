# Native failure-only UDP namespace counters

Measured split-guest-core2048 failures retain destination live-socket drops,
but socket counters do not name the loss reason. Observer-off control also
fails, so do not assume the optional memory observer is the sole cause.

Bounded diagnostic only: read at most64KiB of owned PID net/snmp after failure,
inside the existing prior/final PID epoch guard. Parse one IPv4 UDP header/value
pair, distinct named counters and unsigned64-bit values. Preserve cumulative
network-namespace scope; no baseline, per-socket or per-timeout attribution.
Missing/malformed SNMP is UNAVAILABLE without invalidating valid socket data.
No normal workload sampling, protocol/security/production or timeout change.

8 literal RED tests then focused tests/Ruff, actual Linux owned-socket smoke,
one scoped review. Commit, release build, then fixed3 observer-off2048 diagnostic
trials with all failures retained. Do not resize buffers or claim causality from
namespace totals alone. Record possible resource/CPU overlap explicitly.
