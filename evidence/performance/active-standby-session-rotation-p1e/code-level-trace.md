# P1E code-level ownership and protocol trace

## Outcome

**C — CODE-LEVEL PROTOCOL BLOCKED.** The approved ownership decision assigns active/standby lifecycle and fresh RouteGrant acquisition to a production Go client/agent. No such component or acquisition contract exists in this repository. Implementing it would require choosing a new application API and/or a new authority-acquisition exchange that the frozen protocol does not define.

## Go ownership inventory

The complete repository contains exactly two Go modules:

1. `interop/nbsr-go-peer`: an independent cross-implementation source peer created for interoperability and performance evidence. Its approved plan calls it a standalone module and a test process and explicitly preserves a no-production-readiness claim.
2. `verifiers/federation-go`: a standard-library verifier for frozen Federation packages. It has no QUIC client or application-flow ownership.

There are no `.go` files outside `interop/` and `verifiers/`. Therefore there is no production application-facing Go client/agent, service cache, RouteGrant client, or session lifecycle owner to extend.

## Actual RouteGrant path

The only wire-capable Go peer reads authority from files:

- `config.F75Package` and `config.LifecycleAuthorityDir` are filesystem paths (`main.go:34,41`).
- The single-session path reads `<F75Package>/route-open-body.cbor` (`main.go:384`).
- The lifecycle benchmark reads `<LifecycleAuthorityDir>/<service>/route-open-body.cbor` (`main.go:703,719`).
- It extracts the exact embedded grant and verifies it locally before sending `ROUTE_OPEN` (`main.go:393-422,729-748`).

This is checked-in/test-generated authority consumption, not RouteGrant acquisition. No Go interface requests or renews a grant from a Name Node or client authority service.

## Frozen Core message inventory

Rust Core v0.2 defines `CLIENT_HELLO`, `EDGE_HELLO`, `ROUTE_OPEN`, `ROUTE_ACCEPT`, `ROUTE_REJECT`, `STREAM_OPEN`, `STREAM_ACCEPT`, `STREAM_REJECT`, datagram messages, `ROUTE_DRAIN`, `ROUTE_REVOKE`, and `ROUTE_CLOSE` (`core_v02.rs:39-51,898-908`). The Go peer implements the first eight messages. Neither implementation defines a RouteGrant request, response, renewal, or replacement-authority exchange.

`ROUTE_OPEN` carries an already-issued immutable RouteGrant; it does not acquire one. A fresh TS-B needs fresh client-session-key binding, grant nonce, route/channel identifiers, F75 proof, and Federation authority before it can send that message. The repository has no live producer for those inputs.

## Rust hard-cap trace

A server cap alone is technically expressible without a wire change:

- `ChannelStreams.prepare_open` already checks committed replay membership before mutation (`channel_streams.rs:47-72`).
- The limit check could occur after duplicate detection and before `StreamGate`/commit.
- `StreamReject::OverCapacity` already represents typed resource exhaustion (`stream_gate.rs:6-15`).
- `ControlSession::authorize_stream_open` already audits `OverCapacity` and returns before commit (`session.rs:589-620`).
- Actual Quinn application stream exposure occurs only after control admission and permit validation, so this is the pre-side-effect boundary.

However, P1E defines one coordinated fix: Go proactive rotation plus the Rust hard cap. Implementing only the cap would protect the server but would not implement ACTIVE/STANDBY ownership, fresh TS-B authority, atomic selection, bounded retry, or cross-generation revocation. It would also make the requested five-pair and long Go-to-Rust rotation proof impossible. The task's implementation gate prohibits inventing the missing contract, so no partial production edit was made.

## Why the interoperability peer cannot be silently promoted

`interop/nbsr-go-peer` is intentionally independent test code. Its lifecycle mode opens a configured number of sequential connections and consumes pre-generated authority directories. It has no application-facing ownership scope, no fresh authority provider, no active/standby selector, no revocation feed, and no retry contract. Refactoring it into a production client would reverse its frozen isolation/non-claim and require selecting a new public package/API plus production authority source. The approved ownership allocation says who owns these decisions; it does not supply their missing interface semantics.

## Exact missing contract

Freeze a production Go client/agent package and an authority-provider interface that returns freshly issued, TS-specific RouteGrant/F75/Federation inputs for a named service and authenticated session key. The contract must specify:

- caller and provider identity/trust boundary;
- request inputs and binding to the new session public key;
- response authority, expiry, revocation, uniqueness, and failure types;
- whether acquisition is local IPC/API or a new NBSR wire exchange;
- atomic service ownership scope and cross-generation revocation feed;
- retry and cancellation behavior without reusing failed authority.

If it is a new NBSR exchange, message codes, schemas, transcript bindings, replay rules, and downgrade behavior require a separate frozen protocol decision. If it is a local application API, its exact interface and production component location still must be frozen before implementation.
