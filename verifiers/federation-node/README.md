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

## Explicit authority package versions

Default CLI and API verification remains immutable `federation-v0.1-development-v1`
with manifest pin `1ff9591b925e926e757bb57ab8f3cd1620b6ff9d41149df92ad5672ff810ab35`.
The original development registry is verified from its archived snapshot, never
silently replaced by the current registry. Select the approved v2 explicitly:

```text
node src/verifier.js --version federation-v0.1-development-v2 ../../vectors/federation-v0.1-development-v2
```

`verifyPackage(path, version)` and `loadAuthorities(path, version)` require the
same explicit v2 selection. The latter always authenticates the manifest; it
accepts no caller-provided lock map. V2 manifest pin is
`06511cfffacc2ced7f350d54edab86cd214e369f140ab45f32139ed94a556532`.
Purpose 15 (outer ACP results) and 16 (enrollment results) remain distinct and
cannot replace federation signing purposes. Recognition is not runtime conformance.
