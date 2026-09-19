# Destination readiness-to-socket port gate

COMPLETE: narrow offline evidence-validator repair. The old pair gate checked
observed local address, process identity and attempt history, but did not join
the destination socket port to its declared readiness endpoint. Two deliberately
resealed fixtures passed incorrectly: changing the observed destination port and
changing all mutually matching readiness/source-endpoint declarations instead.
This is a validator gap, not a measured production security defect.

Literal RED: both wrong-port cases fail to reject; valid multiple-socket case
passes. The new gate requires at least one retained destination owned socket to
match the exact readiness IPv4 address AND port. It does not assume the first
socket is the matching one. GREEN: 81 affected history/socket/pair/cohort/fixed-work
tests PASS; scoped Ruff PASS. Uninstrumented historical evidence stays unchanged.

Checker b74bb2b5 revalidates all ten original 11677eca measurement cells, five
Direct/NBSR pairs, read-only. Their source checksums remain unchanged; all ten
destination readiness endpoints match the retained live observations. No new
workload, release build, runtime/capture modification, timeout change or protocol
security change occurred. This adds no throughput or physical-host claim.

Source ephemeral port attribution still requires the separate exact packet-tuple
join already retained by the live coordinator. Whole-flow continuous/exclusive
ownership and traffic phase separation remain unproven. Next planned campaign
step after reset remains phase separation, followed by the broader closure list.
