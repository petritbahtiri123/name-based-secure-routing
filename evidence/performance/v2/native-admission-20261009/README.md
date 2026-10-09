# Native lifecycle evidence: 2026-10-09

Public-safe evidence from the local NBSR admission/teardown investigation.
This package does not publish the uncommitted transport patch as repository code.
The separately published root `AGENTS.md` is portable project guidance.

## Provenance and limits

- Base commit: `6c75e4f152c0b5ca82d7ca6152feee379bfad095`.
- Binaries came from uncommitted worktree snapshots, not the bare base commit.
  `summary.json` and the ZIP manifests retain source/patch/binary SHA-256 hashes.
- Same-host Linux containers on the Windows laptop; 100 offered clients/s,
  two source shards, two destination runtime workers, fixed CPU pools and
  1,024-byte payloads. Validators and deadlines were unchanged.
- Instrumented baseline: one admission slot. Candidate: two bounded admission
  slots. Neither result establishes multi-host/WAN performance or capacity.

## Results, including failures

| Case | Workload result | Outer collection/cleanup |
| --- | --- | --- |
| Instrumented 16 clients | Paired PASS; ownership zero on both sides | 19.820 s total |
| Instrumented 4096, one slot | INVALID_PARTIAL; 3706 active per endpoint, 25 source handshake timeouts, no roundtrips/release | STOPPED_OUTER_DEADLINE; 99.303 s total |
| Two-slot 16 clients | Paired PASS; ownership zero on both sides | 18.023 s total |
| Two-slot 4096 | Both endpoints PASS; 4096 active each, 4096 unique source roundtrips and destination samples; no logged handshake/close errors; all 11 ownership counters zero on both sides | STOPPED_OUTER_DEADLINE during collection; 98.996 s total |

The final 4096 coordinator did **not** produce its aggregate paired PASS record
before the 95-second work cap. Its endpoint processes and management relays
exited successfully before the cap. Complete settled endpoint archives were
retained and all original inventory entries verified (source 16403, destination
8213). Do not relabel the outer cap as PASS or infer repeatable capacity.
The older October 5 close failure did not recur in this attempt; its exact
original QUIC cause remains unknown. No extra large run was made automatically.

The controlled stalled-handshake probe passed. Expected-red tests for missing
close categories and the old admission default are retained alongside passing
runs. Final focused verification: 20 Rust tests, 29 Python tests, offline cached
Linux build, and the 16-client gate passed. All task containers were removed;
managed host-process counts were zero after each bounded run.

## Contents and integrity

`evidence-public.zip` contains allowlisted commands/configuration, build identities,
complete PASS/FAIL reports, endpoint logs and counters, management events, test
logs, original checksum indexes, and a public manifest. The public manifest gives
both original and published hashes for sanitized entries. Environment records
are explicitly projected; personal user-home paths are redacted.

Private fixture credentials, keys/certificates, capability bytes, executable
binaries, caches, source tarballs/bundles and full patch contents are excluded.
Seven complete local-only ZIPs preserve the original continuation evidence,
including private test fixtures; their hashes and sizes are recorded in the
public manifest. Those private archives and originals were not uploaded or deleted.

Verify the public ZIP against `checksums.sha256`, then its internal checksum file
and `PUBLIC-MANIFEST.json`. Original indexes describe original bytes, not the
sanitized replacements. Checksums detect corruption; they are not attestation.

The public ZIP was opened and every member verified before publication.
GitHub availability must be checked at the exact publication commit before
calling this an online backup. Publication metadata is separate from these
immutable measured outcomes.
