# NBSR Core v0.2 Node.js vector verifier

This dependency-free Node.js 24 tool independently verifies the checked-in
`vectors/core-v0.2` conformance package.

Run from the repository root:

```powershell
node --test tools/core-v02-node-verifier/test/verifier.test.mjs
node tools/core-v02-node-verifier/verify.mjs vectors/core-v0.2
```

The verifier checks the strict manifest and package inventory, safe paths,
lengths, SHA-256 values, bounded RFC 8949 deterministic CBOR, COSE Sign1,
Ed25519 Route Open proof bytes, all 32 artifact outcomes, and the fixed
eight-scenario catalog.

The tool reads but never writes the vector package. It has no npm dependencies,
does not execute or import Python or NBSR runtime code, and reads only the two
public test keys. The checked-in private test seeds are not read.

This is a second-language conformance verifier, not an NBSR runtime
implementation. Passing it demonstrates cross-language agreement for the
approved deterministic vector package only. It does not prove production
readiness and does not authorize WP3, QUIC integration, or changes to frozen
Core registries and schemas.
