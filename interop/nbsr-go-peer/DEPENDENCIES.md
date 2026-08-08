# Task 10B independent Go peer dependency evidence

Status: feasibility GREEN; Task 10B route/stream interoperability, final
conformance, and both independent reviews pass.

## Selected transport engine

- Go 1.26.5 on Windows amd64.
- quic-go v0.61.0, released as an upstream tagged module.
- Module checksum: `h1:ui88A53s8MSVYLC56en0KQ17HARk+9986Dn0SBfKNvA=`.
- Module `go` requirement: 1.25.0; executed successfully with Go 1.26.5.
- License: MIT. The upstream `LICENSE` SHA-256 is
  `77d0b7b53e8abb84cf4dd3f9945a7fdf27044240d2e8023966a721a9a46fe96e`.
- quic-go is transport machinery only. It supplies no NBSR encoding,
  validation, authority, state-machine, correlation, or expected outcome.

The exact direct dependency is `github.com/quic-go/quic-go v0.61.0`.
The selected module graph resolves `golang.org/x/crypto v0.54.0`,
`golang.org/x/net v0.56.0`, and `golang.org/x/sys v0.47.0` as indirect
requirements. The linked proof binary imports quic-go, x/crypto, and x/sys;
the complete module and package inventories were inspected from `go list`.
There is no local `replace`, editable dependency, cgo, Rust dependency,
repository Python dependency, or Task 9 verifier dependency.

## Executed disposable proof

Disposable proof command:

```powershell
go build -trimpath -o proof.exe .
proof.exe <generated-test-authority-directory> 127.0.0.1:<rust-port> vectors/core-v0.2/wp4-exporter/valid/service-channel-tcp-01/context.cbor
```

The proof was created and executed outside the repository under
`%LOCALAPPDATA%\Temp\nbsr-task10b-quicgo`. The peer used only the public path
`quic.ConnectionState().TLS.ExportKeyingMaterial`. The Rust/Quinn peer derived
its value independently and disclosed only its post-handshake SHA-256 digest.

- QUIC v1: PASS
- TLS 1.3: PASS (`tls.VersionTLS13`, numeric value 772)
- exact ALPN `nbsr-quic-1`: PASS
- mutual TLS: PASS
- bidirectional stream IDs: PASS (first client bidirectional stream ID 0)
- 0-RTT disabled: PASS (`Allow0RTT=false`, `Used0RTT=false`)
- public TLS exporter: PASS
- exact frozen exporter label/context/output length: PASS
- Go/Rust exporter parity: PASS
- key logging disabled: PASS
- unsupported ALPN: REJECTED
- wrong certificate identity: REJECTED
- wrong CA: REJECTED
- missing client certificate: REJECTED
- unrelated exporter label: separated output
- changed exporter context: separated output

Both peers produced exporter SHA-256
`b652abbaae005fb6a25a0652a452b31daee80c2710918c0a20f94c59c67dcc01`.
The compared exporter bytes were derived independently after the handshake;
neither peer received expected exporter bytes or a precomputed acceptance
label from the other.

The checked result is `feasibility-result.json`, SHA-256
`59182c2dea870ef7a1e242822b6bd3b0f8e23e5084c47e981196002f37f81f54`.

## Dependency and security inspection

- `go mod verify`: PASS (`all modules verified`).
- `go test ./...`: PASS.
- `go vet ./...`: PASS.
- `govulncheck: PASS` using `golang.org/x/vuln/cmd/govulncheck@v1.6.0`.
- Reachable symbol vulnerabilities: 0.
- Imported-package vulnerabilities: 0.
- One module-only advisory, GO-2026-5932 for the unmaintained
  `golang.org/x/crypto/openpgp` package, was reported as unreachable and that
  package is not imported by the peer.
- Public-API source scan found no imports of quic-go `internal` packages and
  no `unsafe`, reflection, private key schedule, copied TLS secret, or debug
  key-log use.

## Rejected Python candidate

aioquic 1.3.0: REJECTED. A disposable Python 3.14.6 proof passed exact ALPN,
mTLS client behavior, bidirectional streams, and disabled 0-RTT, but aioquic
exposed no supported public TLS exporter API. Task 10B will not fork or patch
aioquic and will not access its private TLS key-schedule state. No Python
independent peer or aioquic repository dependency was created.
