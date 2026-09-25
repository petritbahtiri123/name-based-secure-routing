# Native live-bundle diagnostic continuation

The native c5b53c66 idle cohort completes three repeats at16..512 but1024-r1
fails with observed negotiated idle expiry during the deliberate hold. Preserve
that failure. Do not increase timeouts or relabel it as a live-workload result.

Port the already-approved B3_LIVE_BUNDLES scenario to the native coordinator:
optional `bundle_mode` exactly `idle-bundles` (default) or `live-bundles`.
The latter adds only the existing benchmark-harness source QUIC keepalive flag
at one second. Destination behavior, authentication, holds, offered100/s,
two source shards, count bounds16..1024 and120-second controller stay unchanged.
No Rust/production change. Sequential cycles reject the live-bundle mode.

Bind mode through config, endpoint CLI/controller, peer environment, exact
source argv and independent replay. Default evidence remains compatible.
Literal RED for mode/command/replay mismatches, then focused tests/Ruff and
one scoped review. Commit before release build and fresh namespace trials.

Run separate live-bundle512 and1024 cells, at least3 repeats; extend5 if active
or destination-cooldown private CV exceeds5%. Use one advertised guest core
per role and the opt-in one-Hz diagnostic observer. Retain failures, stop to
attribute them; no observer-neutral timing or sustainable-capacity claim.
Final ownership and PID absence required. Source cooldown stays NOT_MEASURED.
Keep idle and keepalive results separate, including in claim labels and indexes.
