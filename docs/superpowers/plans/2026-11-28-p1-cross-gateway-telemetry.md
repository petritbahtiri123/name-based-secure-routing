# P1 local cross-gateway telemetry implementation plan

The user authorized building the missing composition on
`codex/p1-cross-gateway-telemetry`, based on `840fef10d`, without publication or
VM/Performance Lab/20k controller interaction.

## Design and scope

Reuse two independent `NameRelay` instances, real ephemeral IPv4-loopback
listeners, existing signed name bindings, session proofs and local registries.
The client authenticates to A, then to B through A's opaque tunnel. Use separate
TLS certificates/trust contexts; inner client-to-B TLS travels through A.
B alone connects to a small TCP service. This is the Python ISP-profile relay
composition, not the Go/Rust Core/Federation demo or a production deployment.
The initial gateway instances shared one process. The authorized successor runs
A and B in separate local subprocesses, checks distinct PIDs privately and joins
both on cleanup. The client/service stay in the supervisor; there is no cross-host
claim. Static loopback DNS/port mapping and local trust are explicit
fixtures; admission, network traffic, policy decisions and service receipt are real.

No production wire fields or admission logic change. A harness-only observer
wraps existing admission/connect methods. Per the user's follow-up, keep each
component's diagnostic ID local; send no trace ID on the wire. The test collector
joins exact private hop handshakes with service observations. A separate private
application challenge verifies the response and is never exported as telemetry.
Never export handshakes, nonces, tokens, keys, addresses, payloads or exceptions.
Emit only closed stage names, local IDs and counted observations.

## Sequential implementation

- [x] Add focused tests in `tests/demo/test_cross_gateway_telemetry.py`; observe
  the missing harness failure.
- [x] Implement `scripts/demo/cross_gateway_telemetry.py`: live success, B local
  registry denial, and real connection refusal at B's reserved non-listening
  socket. Assert service observations 1/0/0 and actual stage correlation.
- [x] Verify privacy and ownership cleanup, distinct per-request IDs, TLS identity
  checks and CLI supervision. Reuse existing relay/evidence tests as neighbors.
- [x] Update demo documentation and root guidance with the exact reproduction
  command and measured scope, preserving the earlier negative inspection.
- [x] Inspect the final diff and perform one scoped correctness/security review.

Use provisioned Python libraries only. Use a 45-second cancellation deadline
plus at most 8 seconds of cleanup (53 seconds total),
own all listeners/tasks and temporary encrypted TLS-key files, and fail rather
than claim success when cleanup or validation is uncertain. No commits or push.

## Separate-process successor

- [x] Require two distinct gateway processes and reaped exits in the regression;
  confirm RED against the old single-process cleanup record.
- [x] Provision worker configuration over private stdin, return private readiness
  over stdout, keep issuer private keys out of gateway workers, and retain
  unchanged relay admission and real TCP/TLS traffic.
- [x] Generate trace IDs in each gateway process, export only local observations
  to the test collector, and retain per-component sequence without inventing a
  global clock/order. Check network writes locally in each worker.
- [x] Verify three cases, cancellation, unexpected B death and forced reap of an
  unresponsive owned worker. Join Windows IOCP accept completion with a bound.
- [x] Preserve the single-process receipt, retain the new measured receipt and
  source hashes, update scope documentation, and complete one scoped review.
