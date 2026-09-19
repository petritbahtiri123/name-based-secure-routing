# Native 512 held-bundle progression

Five original Linux-local control-root cells at a401567d, unchanged 100 offered/s,
two source shards, 1 KiB materialized payload, one guest CPU per role and existing
timeouts: three complete 512/512 with both-endpoint active/release markers,
source ACKs and all eleven final ownership fields zero. Two fail after 511 and
508 source active markers, with respectively one and four observed failed
markers; all reported source errors are retained in analysis.json. Both roles
are cancelled only after failure, so these are incomplete prefixes, not complete
successful/failed-admission accounting. No unfavorable attempt is replaced.

Classification is PARTIAL_FUNCTIONAL_SCALE, not repeat-qualified acceptance.
256 remains the largest five-repeat fully successful native namespace held
cohort in this campaign. The earlier 2048 loopback result has different source,
fixture and placement and remains historical; this does not reduce it to 256.

The unresolved 512 failures do not prove a production or hardware ceiling. No
further optimization, larger timeout, added keepalive or protocol change follows.
No 1024 run is made under unchanged 100/s: launch span plus the active hold is
already longer than the established ten-second idle lifetime. That limitation
belongs to this held fixture, not a production connection-count ceiling.

Timing is diagnostic only. Previous-cohort read-only checksum work overlapped
this run; no controlled idle-host timing or causal speed comparison is claimed.
All trajectories, live binding checks for complete cells, incomplete markers,
errors, cancellation and cleanup evidence remain in the raw checksum index.
