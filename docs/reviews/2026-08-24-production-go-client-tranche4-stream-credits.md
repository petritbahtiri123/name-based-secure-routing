# Production Go client Tranche 4 closure review

Date: 2026-08-24

Branch: `codex/nbsr-v3-wp0-wp1`

Starting SHA: `aaaa0f9585eb8af40a2a8c4d9c963cf1f20cd39c`

Frozen main: `1938154d498b32d81a3564319969430644e8a688`

## Scope and outcome

Tranche 4 adds bounded production Go ownership for accepted P2D Stream Credits
and ACCEPT-gated Application Streams on the already-owned Tranche 3 Service
Channel. It changes no frozen Core/P1F/P2D encoding, admission authority,
RouteGrant semantics, `channel_id`, ALPN, or replay behavior.

The focused review found five Important issues. The scoped re-review confirmed
the authority barrier, pending-admission teardown, atomic credit/capacity checks,
and production Manager interop path, then found three remaining Important
issues. The closure fix pass retires inactive draining epochs, makes concrete
refill lock/read cancellation bounded and fail-closed, adds 128-stream coverage,
and adds live wrong-channel plus replay rejection. A final parent inspection of
those scoped changes found no remaining Critical or Important issue.

## Security properties reviewed

- no payload path before same-stream ACCEPT;
- one-use credit bitmap and no cross-SC/cross-TS reuse;
- at most current plus draining epochs and one pending refill;
- local authority/freshness/revocation validation and final ownership barrier;
- actual QUIC StreamID correlation and duplicate rejection;
- deterministic SC/TS recursive teardown with no orphan descendants;
- no ownership lock across authority validation, QUIC I/O, or admission reads;
- bounded streams, pending admissions, refill state, maps, and logical bytes;
- exact P2D preface/refill/profile behavior and fail-closed Legacy downgrade;
- no rotation/recovery, Synthetic IP, resolver/proxy, or unrelated scope.

## Interoperability evidence

The committed-source real-process run used the production Go Manager ownership
path against the existing Rust gateway. It passed one ordinary stream, a
128-stream same-SC case with two refills through epoch 3, and five fail-closed
negative cases. Rust reported 128 completed 1,024-byte payload operations, two
refills, 32 remaining credits, zero errors, and correct payload. Each negative reported
`APPLICATION_STREAM_REJECTED` and `payload_exposed=false`.

The final artifact is outside OneDrive under
`C:\NBSR-build\tranche4-final-committed\live-run\live-result.json` and records
the exact source commit/tree and binary SHA-256 values.

## Fresh closure validation

- production Go client: `go test ./... -count=1`, UCRT `go test -race ./... -count=1`, and `go vet ./...` — PASS;
- independent Go peer: full tests, UCRT race, and vet — PASS;
- P2D Python regressions: 21 passed;
- focused Rust Stream Credit regressions: 11 passed; full Rust transport suite — PASS;
- real Go-to-Rust interop: seven cases PASS, including 128 sequential streams, two refills, wrong-channel rejection, and replay rejection;
- diff checks and one focused review plus one scoped re-review — no remaining Critical/Important findings after the closure fix pass.

## Nonclaims

No long benchmark, WAN deployment, physical NIC, production capacity,
rotation/recovery, automatic replay, migration, Synthetic IP, DNS interception,
or resolver/proxy integration was implemented or measured.
