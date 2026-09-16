# B5 budget checkpoint: allocator and scheduler diagnostics

This budget increment began at 42% weekly usage and stopped at approximately
49%, reserving room below the user's approximately 50% cap. No benchmark remains
running from these two stages. Start SHA: `7d131c7176488960e6517483f189297027ec46e5`.

Completed commits:

- `2c6b3aaa`: ten allocator-off/on runs, failed results retained, observer not
  qualified for causal performance attribution. See `B5_ALLOCATOR_SAMPLER_RESULTS.md`.
- `e89c301b`: six external scheduler-off/on runs, queue accounting retained,
  observer not qualified for causal performance attribution. See
  `B5_SCHEDULER_DIAGNOSTIC.md` for the bounded next placement experiment.

No production optimization or protocol/security change was justified or made.
Memory/p99 cause remains UNRESOLVED. Neither package establishes a hardware
ceiling, accepted sustained soak, leak, leak absence or stable capacity increase.
Do not repeat these diagnostic cohorts merely to obtain passing results.

Canonical index SHA-256:

- `b5-allocator-sampler-7d131c71`:
  `db5e18b8c1fb39bd43c3df0e543cdba7abf6483aa1d0e88dc21381fe75b435c6`
- `b5-scheduler-2c6b3aaa`:
  `dd4b6053a50b62b4e0e4fdfea8d861dac4aceb360c7a54a2b0bbecfb5f7b8a48`

Fresh final verification passed both packages: 43 indexed canonical files,
45 privacy-scanned files and 863 raw index entries (shared release-build
entries counted per package). All raw evidence and release binaries remain.

Safe cleanup removed only the stopped campaign containers
`nbsr-b5-allocator-7d131c71` and `nbsr-b5-scheduler-2c6b3aaa`, after evidence/hash
verification. Their disposable writable layers totaled 893,911,040 bytes,
approximately 0.832 GiB: reproducible source clones and working binaries.
No raw evidence, images, Git data or user files were deleted. Actual host SSD
recovery is not claimed because Docker's virtual disk may retain allocated
space. Operational record: `C:/NBSR-build/b5-diagnostic-cleanup-20260916.json`.

Main/origin-main remain at `1938154d498b32d81a3564319969430644e8a688`; no push.
Pre-existing edits to the server matrix/Linux validation document and three
untracked OneDrive wire-evidence duplicates were preserved outside these commits.
