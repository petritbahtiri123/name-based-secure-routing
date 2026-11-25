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

## Explicit isolated Docker restart fixture

`docker_trial.py` runs two fixture sessions against one retained Rust Gateway
instance and endpoint. It stops and starts the same Go Connector container;
this is supervisor-driven process restart, not automatic coordinator reconnect.
Both sessions use logical authority time 100 and the same exact-bound synthetic
verifier. Only the expected fixture connection/session IDs vary. No protocol,
production authority, READY or application traffic is enabled.

Build Linux `connector-test` from this Go package with `connector_development`,
and `gateway-test` from Rust's `connector_loopback` integration target, using
provisioned offline caches and the AGENTS.md resource supervisor. The runtime
script does not build and uses `--pull=never`. Supply an existing compatible image:

```text
python interop/nbsr-go-peer/connector/docker_trial.py --image <verified-local-image-id> --artifacts <absolute-worker-directory> --evidence <new-absolute-evidence-directory>
```

The opt-in Rust test is `isolated_docker_connector_restart` (ignored by default).
Default Go/Rust loopback behavior remains unchanged. Docker mode pins one private
IPv4 endpoint, uses an internal network without published ports, read-only binds,
dropped capabilities and bounded containers. Generated test PKI crosses only
private attached stdin/stdout pipes in supervisor memory; Docker logging is
disabled. Never enable raw pipe capture or persist the private fixture line.

The Go worker handles SIGTERM through coordinator cleanup and reports socket
release. Rust retains an ineligible owner and pending cleanup ticket after remote
close; only the supervisor's observed zero exit plus Go cleanup marker permits
exact ticket confirmation. Those confirmations are test orchestration, not a
real authenticated backend-completion provider. The second fresh session must
reach generation 2 while Gateway StartedAt and Connector container ID stay fixed.
Both stops and final Gateway socket release are checked. Work stops by 95 seconds;
cleanup and inventory reconciliation must finish within 120 seconds.

Run `TestDockerAddressOptIn` and the existing connector/CBOR neighbors after edits.
Retain every failed trial, source/binary hashes, redacted logs and cleanup receipt.
Stage 3 remains open; registration at real authority is not established.

Add `--first-stop kill` for the abrupt-death variant. The first accepted Connector
receives `docker kill --signal SIGKILL`; the second session still stops gracefully.
Require exit 137, PID zero, no OOM, no Go graceful-cleanup marker and removal of
that container's network endpoint. Gateway observes QUIC idle timeout, retains an
ineligible owner/pending ticket, drains its connection and requires the distinct
supervisor `CONFIRM_KILL` before releasing ownership. A process-exit observation
is not a Go cleanup callback; local Go state after SIGKILL is unobservable.
Restart remains supervisor-driven with a fresh session on the same Gateway.
Keep graceful and killed evidence separate; this does not prove instantaneous
failure detection, durable crash recovery, real authority or production readiness.

`--first-stop network` disconnects only the accepted Connector from its task-owned
Docker network, waits for Gateway QUIC timeout/retained ownership, then reconnects
the same running process at its original IP. Container ID, PID and StartedAt must
remain unchanged. During a two-second post-restoration observation, Gateway must
receive no new QUIC connection and retain the same ineligible owner/pending ticket.
This bounded observation is not proof of indefinite absence of reconnects.
Network restoration does not authorize cleanup confirmation. The supervisor then
explicitly stops the original process, verifies graceful cleanup and confirms the
ticket, before restarting with a fresh session (generation 2). Distinguish restored
Docker connectivity from restored registration; this fixture has no automatic
reconnect loop. No Go-local ownership observation is inferred while it is running.

`--first-stop auto-network` uses the separate, opt-in
`TestDevelopmentDockerReconnectProcess` worker. After transport loss it closes
the old coordinator/transport/socket and reports local owner_count=0, then waits
on private supervisor stdin. The supervisor restores the network and observes a
two-second no-new-connection window while Gateway retains its old owner/ticket.
Only after local cleanup and Gateway connection drain does it confirm that exact
ticket. Gateway emits the next fixture with `PreviousCleanupSession` only after
releasing ownership. The worker checks this parent-only receipt against its old
session and requires a distinct nonzero next session before opening any new
socket/coordinator. Missing/wrong confirmation or failed local cleanup forbids
replacement. This receipt is test IPC, not a new wire message or real authority.

The same Connector PID/container and Gateway instance must reach generation 2 by default;
there is no process restart between sessions. Only the final session receives
SIGTERM. This is a bounded automatic recovery fixture with trusted
supervisor coordination, not a production reconnect loop or runtime activation.
Run `TestDockerReconnectGate` with the existing connector/CBOR checks; retain the
historical explicit-restart evidence separately.

Use `--first-stop auto-network --cycles 5` for five network-loss/restoration
cycles and six accepted sessions (generations 1 through 6). Cycle counts are
bounded to 1–5 in the supervisor and both workers; other modes require one cycle.
Every cycle repeats the exact previous-session receipt/local-cleanup gate and the
two-second no-new-connection observation before Gateway cleanup confirmation.
Reports retain all `network_disruptions` and `automatic_reconnections`, not just
the final state. Go's total worker timeout is 90 seconds; the unchanged supervisor
stops work by 95 seconds and includes cleanup within 120 seconds. Five successes
are not an unbounded retry, soak, capacity or durability claim.

`--first-stop auto-network --cleanup-failure` runs one bounded failure/retry cycle.
After actual transport drain and Connector local cleanup, the Gateway injects a
synthetic failed completion callback. The exact ineligible owner must survive
both failure and retry-pending states, each observed for two seconds without a
new QUIC connection. A late success on the failed ticket cannot overwrite its
result; after explicit retry, the old ticket is rejected as stale. Only successful
confirmation of the new exact ticket releases ownership and permits the next
private fixture/session. This tests supervisor-coordinated gating, not an actual
backend cleanup failure or rejection of arbitrary hostile connection attempts.
Authority remains synthetic; no production protocol or READY claim is added.

The `go` CI profile runs the eight stdlib supervisor unit checks via unittest
discovery, plus the existing tagged Go package tests/vet. Rust CI compiles the
ignored Docker target but does not execute it; live Docker trials remain explicit.
