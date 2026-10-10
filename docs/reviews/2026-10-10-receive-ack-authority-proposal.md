# Proposed receive/ACK source authority (inactive)

Local source/evidence commit: `2cc01bede62b43535ef5f69e241e8d9e79bc9b26`. Parent published baseline: `b6afdcdfe6daa85f50d633461df050d0e870ee7f`. Exact eight-file commit scope is in adjacent JSON. No authority files or validators were modified; no push occurred.

The current lifecycle authority pins source `99ac954e0c0d90a221b42492a59fa4d5b962ea5d`. It accepts the adapter before the reviewed two-guard correction. Tests passing does not authorize different source bytes. Replacing that old hash in place would destroy the historical binding.

Proposed additive successor: `NBSR-RECEIVE-ACK-DROP-2026-10-10`, at `docs/protocol/registries/core-v0.2-receive-ack-drop-overlay.json`. Parent registry SHA-256: `d6cc7cf54e0e4752e5662c9a8ee049cb869c3797f4c4770175bf273db9992a79`. Bind the exact source commit above and override exactly one inherited file:

| Binding | Length | SHA-256 |
| --- | ---: | --- |
| Existing quinn_adapter.rs | 95878 | `c0937c20ae437dcf4f598d117704830a458defc109d1b3900e4560c3d9ba0b92` |
| Proposed quinn_adapter.rs | 96452 | `088ce7bc101a5ab0f045fbc68d439e82c516d4cdef0644f92057a8297acb8806` |

All six other selected transport files retain their current hashes: lib.rs, owned_send.rs, udp_socket.rs, benchmark_bind.rs, Cargo.toml and Cargo.lock. Preserve the complete 110-file legacy inventory, ancestor authority chain and historical evidence/validators. Test-source changes remain evidence only. This is selected-source authority, not whole-crate certification.

Approval would authorize creating this additive registry and a separate explicitly pinned validator, switching only the current-source gate to that successor, adding focused acceptance/rejection tests, and maintaining related guidance/evidence. Exact paths and invariants are in the JSON. No missing-file fallback or authority-scope expansion is permitted. Historical tests continue validating their original snapshots. Validation and independent review precede any final integration/publication request.

Approval requested: authorize this exact successor binding and bounded validator/test/docs implementation. Publication/bypass remains a separate approval for the final reviewed commit(s).

## One read-only neighboring check

Inspected paused owned-send cleanup on remote close. Existing test calls drive again after close before checking release; it does not prove eager cleanup without repoll. The API explicitly permits paused ownership/quota retention until abort/drop or further drive. This is a characterization gap, not a verified defect, and no additional implementation/test was started. Any eager-release guarantee requires a separate lifecycle decision.

Local commit emitted the existing worktree-metadata cleanup permission warning; exit was successful and exact commit/file scope was verified. Unrelated untracked files are preserved. Prior test evidence was reused after confirming unchanged source hashes; no expensive tests repeated.
