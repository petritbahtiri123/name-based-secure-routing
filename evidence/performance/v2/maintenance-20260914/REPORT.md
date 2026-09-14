# Campaign cleanup — 2026-09-14

User requested safe SSD and obsolete Docker-image cleanup during the campaign.
No authoritative evidence, source, Git history or personal files were deleted.

Seven verified Cargo targets under `C:/NBSR-build` were cleaned with explicit
`cargo clean --locked --manifest-path crates/nbsr-transport/Cargo.toml
--target-dir <exact-target>` commands: b3-red, b3-baseline, b3-memory, b2-cpu,
b5-soak, b1-wire-overhead and b5-verify, each ending in `/cargo-target`.
All had Cargo cache signatures, no reparse points, empty temporary directories
and only known generated outputs. No Cargo or benchmark process was active.
31 release executable/PDB files were copied and hash-verified first under
`C:/NBSR-build/cleanup-retained-binaries-20260914` (107823104 bytes).

Observed Windows free space rose from 7413743616 to 9829208064 bytes, about
2.42 GB; this delta also includes concurrent Docker allocations. The initial
grouped Remove-Item command was rejected by automatic policy and never ran.
The supported exact-target Cargo cleanup subsequently completed successfully.

Docker cleanup removed nine obsolete ISP r3–r6/diagnostic images, plus the
superseded 6227fd86 smoke image and its two stopped containers. Container diffs
were empty; their logs and inspect metadata were retained. The named
`nbsr-linux-smoke-6227fd86-evidence` volume was retained and verified afterward.
Seven exact BuildKit cache IDs belonging to that obsolete smoke-image chain
were removed, reclaiming approximately 2.79 GB inside Docker. No broad prune,
volume removal, unrelated image deletion or virtual-disk compaction was used.

Current benchmark runtime/build/Go/clippy images and accepted ISP r7 images
remain. Windows free space after Docker cleanup was 9814192128 bytes: Docker
internal reclamation is not an additional claim of host SSD space recovered.

Logs, image identities, cache selections and retained-binary hashes are indexed
in `evidence/performance/v2/maintenance-20260914`. Cleanup is infrastructure
maintenance, not a benchmark optimization or a reason to discard valid failures.
