# Native live socket observation

For a diagnostic ownership run, add `--observe-socket-ownership` to both existing
`scripts.performance.linux_native_peer` commands. The default is off. The peer
wrapper already owns and verifies its child executable; the optional observer
uses the retained PID/start epoch to inspect only that process's FD table and
IPv4 UDP bindings. No capability, root requirement or security-policy change is
introduced. Permission failure remains UNAVAILABLE, never inferred ownership.

The observer checks live PID/start epoch, executable and network namespace
before/after reading the table, then rechecks each matched FD/inode. It accepts
only a concrete local address matching the requested benchmark bind. At most
twenty observations occur through the existing 100 ms resource sampling loop;
the first successful observation is retained and sampling stops. No benchmark
timeout is extended. Every unsuccessful observation is retained in
`socket-observations.ndjson`; the successful snapshot is
`socket-ownership.json`. If no binding is observed, the requested diagnostic
run fails rather than claiming ownership.

Native pair validation requires the retained snapshot when this mode is enabled.
Both peer modes must match, and cohort comparison keeps observer-enabled and
observer-disabled runs separate. Existing uninstrumented evidence remains valid
under its original scope. All timing with this additional observer is diagnostic;
no observer-neutral performance qualification is implied.

To join packet accounting, call `linux_socket_ownership.validate_binding` with:

- the retained snapshot;
- expected PID from the owned peer's `pid.json`;
- start ticks from its independently retained resource samples;
- exact executable from its verified `command.json`;
- source `client` or destination `server` address/port from native packet accounting.

Require the observation interval to lie within the retained live process sampling
interval and verify both evidence checksum inventories first. The local endpoint
must match exactly; selecting the first socket or accepting a wildcard does not
establish a captured-flow binding. The snapshot itself is not remote attestation.

This proves an observed live FD binding to the captured local endpoint at a
specific interval. It does not prove exclusive ownership, continuous ownership
of every packet, application handling of each datagram, remote peer identity,
graceful resource cleanup, phase separation or physical-NIC behavior. Unconnected
QUIC UDP sockets do not provide the remote flow identity in the local UDP table.
Keep the existing TLS/authority, exact-tuple, marker, zero-loss and peer completion
gates; this observation replaces none of them.

## Retained validation

Source `11677eca`: five counterbalanced Direct/NBSR pairs at 1 KiB/64 streams,
1000 operations per stream, depth one, zero warmup. Ten of ten cells and twenty
of twenty source/destination endpoint joins pass; eighty wrong PID/start epoch/
binary/port joins reject. Both peers run as UID 65532. Captures also pass existing
marker, zero-loss, exact-tuple and independent TShark accounting gates. The peer
and cohort validators pass after the live run. The three rebuilt release Rust
binary hashes remain unchanged. Focused suite: 90 tests PASS, scoped Ruff PASS.

[Canonical evidence and raw checksum references](../../evidence/performance/v2/native-socket-11677eca/summary.md).
The preceding uninstrumented packet cohort remains separate; no timing or
capacity comparison pools these different observer modes.
