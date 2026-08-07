# Independent Node.js Federation v0.1 verifier

This dependency-free Node 24 verifier independently consumes the checked-in
`vectors/federation-v0.1/` package. It does not import, execute, or shell out to
Python and does not invoke the Task 7 generator.

It verifies the closed manifest before semantics using strict duplicate-aware
JSON, pre-allocation byte limits, stable regular-file handles, exact inventory,
and independently checked authority locks. It then verifies bounded
deterministic CBOR, SHA-256, the fixed Operator ID and Bech32m encoding, tagged
COSE Sign1 with Node Ed25519 and a pinned public test key, all 18 schema classes,
threshold-container v1, capability 6, error precedence, and a minimal typed
deterministic state model. Expected result fields and descriptive case names are
used only for final comparison, never to derive a decision.

Run from this directory with Node 24:

```text
npm test
npm run verify
```

The verifier has no runtime or development dependencies and performs no
network access.

## Non-claims

This proves independent Node conformance against the deterministic Federation
v0.1 Development Profile package. It does not prove Go clean-room conformance,
Rust transport integration, live two-operator federation, production
governance, or production threshold key custody.
