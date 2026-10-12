# Connector development fixtures

This is the approved **code-only, in-memory**
`connector-registration-development-v1` slice. All Go source requires the
`connector_development` build tag; no runtime imports it. Its location in the
existing interop module permits reuse of the strict internal CBOR codec without
an import-boundary bypass or frozen dependency change. Production client
integration remains future work. The Rust modules compile only inside the two
new integration tests and are not exported by the transport library.

The separate registry is
`docs/protocol/registries/connector-registration-development-v1.json`.
ALPN is `nbsr-connector-dev-1`, connector envelope version is 1, and REQUEST,
CHALLENGE, PROOF, ACCEPT, REJECT, WITHDRAW use 24576 through 24581 respectively.
`CONNECTOR_REGISTER=24576` is a connector-local register/renew action; it grants
no publication, delegation, routes or application admission. Core/Federation
registries and signer purposes 14/6/11 remain unchanged.

Independent Go/Rust codecs consume the same 25 retained vectors: 6 accepted,
19 rejected. These are byte/schema checks, not live session interoperability.
Go takes explicit Clock, Dialer, Peer and Authority fixtures. Rust takes an
explicit service/principal policy, clock sample, authority receipt/revision
provider and transport fixture. Missing authority fails closed. Failed cleanup
retains ownership and cancellation blocks further messages before cleanup.

The one-service Rust owner permits one registration and two connection slots,
four completed results and one pending operation, with constant-size counters
and current-acceptance state. Go permits three explicit dial attempts with
fixture backoff of one and two seconds. A coordinator cannot reconnect or reuse
its session; a new coordinator requires a fresh session after cleanup.
Explicit `Poll`/`poll` drives timer cleanup. Retry keeps the original request,
ID and deadline with a new directional sequence; ACCEPT recovery requires a
prior proof transmission. Renewal retains the handle, checks the prior digest
and cannot resurrect expiry. There is no application-work implementation here.

Tests use labelled non-TLS exporter bytes and synthetic authority receipts.
Callbacks are not real verifiers, clocks, event producers or asynchronous
cancellation. The test-only byte comparison is not a reviewed production crypto
primitive. No sockets, credentials, installed trust, origin traffic, readiness
state or durable storage are present.

Run from the repository root with provisioned caches, offline settings and the
AGENTS.md bounded supervisor/resource limits (at most two workers):

```text
go -C interop/nbsr-go-peer test -tags connector_development ./connector ./internal/cbor -count=1
go -C interop/nbsr-go-peer vet -tags connector_development ./connector
cargo test --locked --offline --manifest-path crates/nbsr-transport/Cargo.toml --features benchmark-harness --jobs 2 --test connector_control --test connector_registration
python scripts/generate_connector_development_vectors.py --check
python -m pytest -q -p no:cacheprovider tests/protocol/test_connector_development_vectors.py tests/protocol/test_connector_registration_vectors.py tests/protocol/test_cbor.py
```

Set `CARGO_TARGET_DIR` to the verified existing platform cache before Cargo and
`PYTHONPATH` to the repository root for the generator. Exact commands, failed
attempts and final hashes are in the dated development review. Stage 3 remains
partial: authenticated transport composition, real authority provenance, safe
async timers/cleanup and independent live Go/Rust exchange remain outstanding.
