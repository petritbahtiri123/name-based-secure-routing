# NBSR Core v0.2 deterministic vectors

This package is test-only and must not be imported by runtime code.
Raw `.cbor`, `.cose`, and `.bin` files are authoritative.
Regenerate with `python scripts/generate_core_v02_vectors.py --write vectors/core-v0.2` and verify with `--check`.

The manifest uses closed enums and exact SHA-256/length assertions. Valid
vectors contain no Origin Endpoint or IP literal. Test seeds are public and
never production keys.

The dependency-free Node.js 24 verifier independently checks the package:

```powershell
node --test tools/core-v02-node-verifier/test/verifier.test.mjs
node tools/core-v02-node-verifier/verify.mjs vectors/core-v0.2
```

**Status:** the Python generator/reference verifier and the independent Node.js
verifier establish cross-language vector agreement for 14 valid artifacts, 18
invalid artifacts, and eight scenario definitions.

This agreement is conformance evidence for the reviewed bytes only. It does not
prove production readiness, implement a second NBSR runtime, authorize WP3, or
change any frozen registry or schema.
