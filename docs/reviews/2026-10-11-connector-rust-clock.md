<!-- Publication derivative; original SHA-256 f489167b2cfffcd7457f7815594f66fd7613a383eebb6643dee7230a43742a55. Personal identifiers removed. Historical hashes, results and commands refer to original local inputs; placeholder commands were not executed. Originals retained locally. -->

# Rust explicit-clock guard — overnight 2026-10-11

Four deterministic tests reproduced backward-time connection admission, pending
proof commit, owner poll and invalid-time eligibility retention. All four failed
before fix and pass afterward. The test-only gateway now stores its observed-time
floor and a failed-clock latch. attach/handle/poll check it before dispatch; bad
time makes retained connections terminal and owner ineligible without releasing
resources or claiming close success. Direct close and exact async completion
remain available; later valid time cannot reset admission on this gateway.

Final Rust scope: **23 passed, zero failed, one ignored** (22 owner/cleanup tests
including4new,1codec; live loopback deliberately ignored). Scoped Clippy with
-D warnings, cargo fmt and diff checks pass. Independent review clear, not rerun.
Five supervised runs retained including4-failure red. Source preimages, final
snapshots, incremental patches, exact commands and current target binary hashes
are in the manifest. The loopback target was recompiled but NOT executed live;
the earlier live results/binary hashes remain historical. No new live proof.

Verified Rust1.97.1/edition2024, locked offline dependencies and existing target
@LOCAL_USER_ROOT@/Documents/Codex/2026-10-04/task/nbsr-handshake-target. Two jobs and
existing95s work/120s cleanup supervisor;8GiB starting disk/6GiB floor, stricter
256MiB growth and2GiB RAM reserve. No abort; all direct children reaped, final
process check found no relevant workers. No sockets/containers/keys/downloads.
AGENTS and Go/Rust fixture README updated. No frozen source/registry modification,
real clock/event producer, lifetime policy or runtime authority change. Stage3
partial, stages1-2 2/10. All changes uncommitted/unpublished; unrelated work kept.
