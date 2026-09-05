# Isolated implementation handoff

Status: stdlib TCP/UDP adapters and closed command entrypoints implemented after literal RED. The full supervisor, connector and seven-service definition now exist; see RUNTIME_TOPOLOGY.md for current integration status. Focused Go tests, race tests, vet and Python tests pass on Windows. No Linux container, Docker topology, or QUIC integration execution is claimed.

## Adapter integration

The new `adapter` module is stdlib-only. It must expose the exact approved `ServeTCP` and `ServeUDP` APIs. TCP upstream is exactly a literal `127.0.0.1:<port>` taken from validated Go readiness. UDP upstream is exactly a literal `127.0.0.1:<port>` from the Rust original readiness. Both limits are 16. TCP uses two fixed copy buffers and one bounded upstream dial per accepted connection; preserve TCP half-close so EOF on the request direction can still receive the response. Cancellation closes and joins all accepted connections. UDP uses one connected upstream socket per exact source address/port, a maximum-size bounded datagram buffer, idle expiry and complete cancellation cleanup. No parsing, retry, target selection, secret access or fallback.

The stricter approved architecture requires binding the listener to the adapter's exact access/transit interface IPv4, not the plan's illustrative `0.0.0.0`. Otherwise a sidecar sharing a runtime namespace would also expose its listener on the runtime's other network. The orchestrator must inspect the named network address and write it to closed adapter configuration. The config must not expose an origin address to ISP-A.

The commands accept exactly `--listen <literal-private-interface-IP:fixed-port> --ready <projection.json>`. Fixed ports are TCP/18080 and UDP/45980. The readiness projection is exactly `{"schema":"nbsr-isp-adapter-ready-v1","transport":"tcp","upstream":"127.0.0.1:54321"}` (use `udp` and the validated Rust loopback port for ISP-B). The orchestrator must generate this endpoint-only projection from the validated original readiness; adapters must never mount/read readiness containing client keys. Unknown/duplicate keys, nonliteral upstreams, wrong transport, extra arguments, malformed/trailing data and files over 4096 bytes fail closed. Both capacities are fixed at 16 and time bounds at 20 seconds. No environment target/fallback option exists.

Build entrypoints from the adapter module with `go build ./cmd/isp-a-tcp` and `go build ./cmd/isp-b-udp`, choosing an external `-o` output directory for retained artifacts. The private interface address is validated by the orchestrator against Compose inspect, then bound by the adapter; the adapter itself cannot identify a Docker network label.

## Integration requirements

1. The fixed-target Origin Connector is under the separate origin-connector directory. It must parse only the existing accepted bounded request, resolve exactly one private-origin IPv4 in the inspected private subnet, dial it once at port 8080, bound all I/O, and emit no successful response on failure. Select it through the existing hashed backend map; do not change the Rust destination.
2. Produce a federation preflight result with closed fields, actual current-SHA tests and digest correlation. Gate every data-plane service/workload on PASS. This is admission preflight, not distributed live-runtime federation.
3. Orchestrate Rust/Go readiness and namespace startup. Retain original Rust readiness; copy only `endpoint` to `isp-b-adapter:45980` and verify all seven immutable fields byte-for-byte. Keep artifacts containing client key material out of public evidence.
4. Give ISP-A only `isp_a_access` and `federation_transit`; give ISP-B only `federation_transit` and `isp_b_private`; origin only private, workload only access. Adapter sidecars share the matching runtime namespace without extra attachment. Supply network aliases on the runtime service when sidecars use namespace sharing.
5. Resolve and record actual immutable Go/Rust/runtime image digests before authoring executable pinned image references. No invented hashes or floating-tag release claims. Use release builders, non-root runtime, read-only rootfs, dropped capabilities, no host ports, no socket mount, no privileged/host networking or firewall changes.
6. The runtime launch interface and artifact mount layout are implemented in supervisor.py and compose.yaml using inspected entrypoints/flags. Container execution remains unverified; do not infer a live PASS from the deployment definition.

The private-origin fixture tests passed; its origin-only fragment remains available for isolated fixture validation. The full Dockerfile/Compose topology is authored. Container configuration/build validation, negative network tests, request counters, exact project cleanup and retained raw evidence remain live acceptance gates. Those live steps have not run.

Verified commands (from `deploy/isp-federation-poc/adapter`):

```text
go test ./... -count=1
go test -race ./... -count=1
go vet ./...
```

The existing frozen authority/protocol/runtime code remains unchanged. No production integration edit is required by the currently defined adapter interfaces.
