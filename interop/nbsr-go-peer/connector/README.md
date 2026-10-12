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
Callbacks are not real verifiers, clocks or event producers. The cleanup adapter
below exercises asynchronous confirmation and cancelled waits, not real transport
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
partial: authenticated transport composition, real authority provenance, real
backend timers/cleanup and independent live Go/Rust exchange remain outstanding.

## Asynchronous cleanup fixture adapter

`CleanupPeer` adapts a prompt, nonblocking callback backend to the existing
`Peer.Close()` contract. One private attempt remains owned until its callback
confirms success or failure. Pending/failure returns an error, so the serialized
coordinator keeps its peer/registration and rejects replacement or resumed proof.
After successful notification, the caller invokes `Coordinator.Close()` again
to apply confirmation. Callbacks never mutate the coordinator.

`WaitCleanup(ctx)` uses a channel notification; cancellation/deadline stops only
the wait. It never assumes the backend stopped or that quota is free. A failed
attempt needs explicit `RetryCleanup()`; pending work cannot be retried. Attempt
identity and first-result retention reject stale and duplicate callbacks. The
adapter creates no goroutine, timer, socket, retry loop or new deadline policy.
The injected backend must return promptly and retain/cancel its own resources;
this fixture does not prove a real backend will complete within a time bound.
Coordinator/start calls remain serialized; callbacks and waiters may be concurrent.

This reuses the existing terminal-before-cleanup and exact-owner rules. It does
not change deny-new versus terminate semantics, active-work grace, Rust cleanup,
or reconnect policy. The deterministic tests include cancellation while waiting,
controlled timeout, late/duplicate callbacks and failed-close ownership retention.

## Rust asynchronous cleanup composition

The test-only `connector_cleanup.rs` adds `CleanupTicket` for the existing Rust
gateway. `begin_cleanup` makes the exact connection terminal and retains its
ticket and owner/quota. A synthetic backend can complete a cloned ticket; that
callback only records the first result and notifies waiters. Repeated begin calls
return the same ticket, not a new backend dispatch. Dispatch and any backend-owned
resources remain the injected caller's responsibility.

Dropping `ticket.wait()` or selecting a caller-supplied deadline never releases
ownership. `finish_cleanup` checks the current private attempt, full session and
existing owner handle/generation before applying confirmed success. Failed
confirmation retains ownership; `retry_cleanup` returns a new ticket only after
an exact failed attempt. Stale/duplicate callbacks cannot release a later owner,
including after numeric connection-ID reuse. Synchronous close, expiry polling
and termination cannot bypass an outstanding ticket.

The waiter registers its notification before inspecting the retained result,
avoiding lost wakes. No worker, busy loop, timer, new backend deadline or active-work
grace is introduced. Rust/Go composition here remains synthetic; neither proves
actual transport termination or authenticated registration. See the consolidated
`docs/reviews/2026-10-10-connector-stage3-code-checkpoint.md` for exact validation,
uncommitted inventory and remaining runtime gates.

## Explicitly authorized loopback integration

`loopback_test.go` and Rust `tests/connector_loopback.rs` compose the development
coordinators with real quic-go/Quinn TLS 1.3 on IPv4 loopback only. The Rust test
is ignored by default; the Go worker skips without its parent-only environment.
No production module imports these test adapters. They retain separate connector
ALPN/exporter domains without changing the frozen Core transport.

With explicit permission for local sockets and temporary test certificates, first
compile the Go worker to a task-owned temporary executable, then set
`NBSR_CONNECTOR_GO_TEST` to its absolute path and run the ignored Rust test:

```text
go -C interop/nbsr-go-peer test -tags connector_development -c -o <temporary-executable> ./connector
cargo test --locked --offline --manifest-path crates/nbsr-transport/Cargo.toml --features benchmark-harness --jobs 2 --test connector_loopback -- --ignored --nocapture
```

Use the AGENTS.md resource guards and process-tree supervisor for each command;
build sequentially. The current-machine commands, supervisor source and all failed
attempts are retained with `docs/reviews/2026-10-10-connector-loopback.json`.
The harness generates one-hour Ed25519 test PKI in memory, passes only child-needed
material over stdin, and installs no trust or credential files. Never retain stdin,
private keys or TLS exporter output. Public process IDs/socket endpoints are evidence.

Authority and revocation remain exact-bound synthetic fixtures, and authority time
is the explicit logical sample 100; TLS certificate validity uses the real clock.
The test proves local control interoperability, not purpose-14 authorization,
signed registration delegation, verified event delivery, production timers, origin
access or Stage 3 closure. The existing deterministic callback/drop tests remain
separate evidence for stale/duplicate completion and failed ownership retention.

Final ACCEPT is acknowledged by the child's control-stream FIN before teardown.
Go closes its transport (joining its reader/handlers) and owned socket before owner
release. Rust waits endpoint idle, drops it, reaps the child and observes UDP socket
release before confirming its retained cleanup ticket. Deadline/forced-kill failure
is not a successful cleanup result. No automatic reconnect or active-work grace is
introduced by this control-only harness.

The development Go coordinator now latches an observed owner expiry in its
retained eligibility state through owner lookup, renewal begin and pending retry.
Rolling a fixture clock back cannot restore that expired acceptance. Ownership
remains retained for explicit cleanup. A subsequent observed-time floor additionally
rejects backward/out-of-range injected clock samples across coordinator paths,
including pending retry and authority callbacks; clock recovery cannot clear its
stop latch. This is still no application-work deadline or real clock provider.
Evidence is in `docs/reviews/2026-10-11-connector-go-expiry.md` and the successor
`docs/reviews/2026-10-11-connector-go-clock.md`; the older loopback binary/run
remains historical and was not rerun for this correction.

The Rust development gateway similarly observes supplied time at attach, handle
and poll. Backward/out-of-range time latches admission off across that serialized
fixture gateway while retaining connections and owner. Direct confirmed cleanup
and exact existing async tickets remain usable; later time cannot reopen admission.
See `docs/reviews/2026-10-11-connector-rust-clock.md`. This is not a live timer.

### October 11 reviewed local checkpoint

Five offline/development fixes and a fresh 19-case Go/Rust loopback pass are
recorded in `docs/benchmarks/OVERNIGHT_ROBUSTNESS_2026-10-11.md`. Latest scoped
results are Python 436 passes, Go 28 top-level passes, and Rust 23 passes plus
one default live ignore. Explicit live execution passed all 19 cases, with child
reap and UDP cleanup confirmed. This supersedes the earlier no-rerun checkpoint
for current-source loopback evidence only; historical records remain unchanged.
Stage 3 remains partial, with real authority/revocation and timers unproven.
