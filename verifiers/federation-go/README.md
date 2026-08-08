# Clean-room Go Federation v0.1 verifier

This Go 1.26 module independently consumes the frozen
`vectors/federation-v0.1/` package. It uses only the Go standard library and
does not execute, import, or shell out to Python, Node.js, their verifiers, or
their generators. Expected outcome fields are read only after Go has computed
its decision.

The verifier closes and authenticates the package before semantics; implements
bounded deterministic CBOR, SHA-256, Operator ID and Bech32m, tagged COSE
Sign1/Ed25519, all 18 object schemas, threshold-evidence v1, authenticated
capability agreement, the 11-rank error precedence, and a Go-owned deterministic
state model for all 43 scenarios.

Signed-vector authority is resolved from manifest-anchored public signer records
using the protected `kid`. Required class and purpose are derived from the signed
payload, including identity-root versus recovery authorization. Operator IDs are
derived from genesis keys while distinct operational Ed25519 keys, subject
bindings, lifecycle, validity, revocation, and authority-state watermarks are
verified independently. Deterministic fixture keys are public test material only.

Run from this directory:

```text
go test ./...
go run ./cmd/verify ../../vectors/federation-v0.1
go vet ./...
```

## Non-claims

This proves a second independent language implementation against the
deterministic Federation v0.1 Development Profile. It does not prove Rust
transport integration, real wire exchange between operators, real DNS/HTTPS
discovery, live federation deployment, production governance/key custody, or
Internet-scale performance.
