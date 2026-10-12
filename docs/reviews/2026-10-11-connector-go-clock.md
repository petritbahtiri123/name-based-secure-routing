# Go injected-clock rollback guard — overnight 2026-10-11

Three deterministic regressions reproduced missing monotonic-time observation:
expired pending retry105->104 recovered a lost ACCEPT; authority callback100->99
reached transport; owner lookup120->110 stayed eligible even before lease expiry.
All three failed before fix and pass afterward. This extends the earlier narrow
owner-expiry latch; its report remains historical and unchanged.

Every coordinator clock read now uses a retained observed-time floor. Invalid or
backward samples set the existing stopped latch and withdraw owner eligibility;
an out-of-range sentinel fails existing deadline guards. Connect uses one sample
for its range check and deadline addition. Peer/pending/owner remain retained until
explicit cleanup, and failed cleanup cannot release them. Later valid time cannot
clear the stop latch. No actual clock provider, thread or new active-work policy.

Final Go connector25 top-level tests/77 pass events; CBOR3 top-level/10 events.
Zero failures; one explicit parent-only live-worker skip. Four new top-level
tests include out-of-range pending/owner subcases. Vet, gofmt and git diff check
pass. Independent review clear, no independent rerun. Four supervised runs,
including3-failure red, retained with commands and source preimages/final patches.
Two documentation patch attempts had incorrect anchors and made no changes;
corrected anchors applied successfully before final checks.

Existing warm Go1.26.5 host cache and module cache reused under offline settings,
two jobs,95s work/120s cleanup,8GiB disk start/6GiB floor, stricter256MiB growth,
2GiB RAM reserve. No abort; all direct children reaped and final process check
found no relevant workers. No new sockets, keys, containers, live run or downloads.
AGENTS/Go README and overnight record updated. No staging/commit/push; historical
manifests and earlier loopback binary are snapshots, not current-source proof.
Stage3 partial, stages1-2 2/10. Rust clock handling remains a separate inspection.
