# Production Go client Tranche 2B 3R-C closure

## Verdict

3R-C is complete and verified. Tranche 3 has not started.

## Scope and commits

- Starting repair SHA: `1d4eabd3082f02cedef2bd06180016c77d883f60`.
- Task 3 blocker repair: `3ecedee71f7bdab1707ef6d7fd98d447fdca821c`.
- Task 4 startup/interoperability: `981564d3fac1a4fade3c0894569b23817057a464`.
- Frozen reference: `main == origin/main == 1938154d498b32d81a3564319969430644e8a688`.

## Task 3 blocker closure

The prior admission path counted 16 ordinary authenticated lifecycles plus a special overload-signing lane, allowing 17. Removing that lane without replacing admission also allowed unsigned HTTP 429 to escape before the protocol could produce an authenticated semantic result.

The repair uses one exact reservation counter capped at 16. A bounded pre-authentication wait honors cancellation and the signed request deadline, then hands the exact reservation atomically into authenticated idempotent processing. Distinct overload returns a signed ACP `resource_exhausted` result with the bound request and operator/profile/version fields and no artifact. Exact duplicates remain capped at four waiters and preserve exact-byte replay.

Literal RED evidence reproduced both `authenticated_lifecycles=17` and unsigned HTTP 429. A later deterministic handoff test reproduced the TOCTOU state `exact=4 active=16`; the repaired handoff retained the reservation until ownership transfer. GREEN tests cover exact cap, multiple overload requests, duplicate bounds, deadlines, cancellation, cleanup, and replay. Maximum observed authenticated lifecycles: 16.

## Task 4 interoperability closure

The real TLS 1.3/HTTP/2 E2E performs bootstrap authorization, ENROLL, result verification, authenticated identity persistence, Freshness, Ready, Acquire, Renew, freshness refresh, restart, authenticated identity reload, a new Freshness validation, and final Ready.

Initial enrollment is a durable one-shot transaction. Before network activity the store writes an authenticated pending envelope while holding the memory/OS lock; verified acceptance atomically replaces it with the identity. A competing runtime makes zero outbound enrollment calls. Ambiguous failure or process death leaves the pending envelope and therefore fails closed instead of risking a divergent remote/local identity.

Restart restores no RouteGrants, authority cache, Transport Sessions, Service Channels, Stream Credits, or Application Streams.

## Fresh acceptance evidence

- `cd client/nbsr-go-client; go test ./... -count=1` — PASS.
- `cd client/nbsr-go-client; $env:PATH='C:\msys64\ucrt64\bin;' + $env:PATH; go test -race ./... -count=1` — PASS.
- `cd client/nbsr-go-client; go vet ./...` — PASS.
- `python -m pytest tests/federation tests/protocol tests/test_route_registry.py tests/test_name_registry.py tests/test_control_plane.py tests/test_name_route_e2e.py -q` with bundled Node on PATH — PASS, `1006 passed in 443.01s`.
- `python -m ruff check scripts/federation_v01_vectors/package.py scripts/verify_wp8_repository_safety.py` — PASS.
- `go test ./internal/authority -run '^$' -fuzz '^FuzzParseVerifiedACPResult$' -fuzztime=10s` — PASS, 25,705 executions.
- `go test ./internal/authority -run '^$' -fuzz '^FuzzParseStoredEnrollmentStateNeverPanics$' -fuzztime=10s` — PASS, 36,037 executions.
- `git diff --check` — PASS.
- ACP SHA-256 — `e795abf0a078c2dfe9bdf56d705fde67a1355bd28eb1cd35b5dc6efb0a5dad24`.
- Enrollment SHA-256 — `9d73983828f48b51a2b2e31c4637f1fe6f00b1505071faeef0be43d0e9504cd0`.

## Reviews and nonclaims

Task 3 and Task 4 each received an independent focused re-review after their regression/fix waves and were CLEAN with no Critical or Important finding. Final whole-scope review is recorded in the closing task report.

This closure proves the bounded Go client/Source Operator control-plane behavior and local real HTTP/2 interoperability in the approved profile. It does not claim production deployment, live external operator interoperability, platform keystore support beyond the separately accepted Windows boundary, restored data-plane state, or any Tranche 3 functionality.
