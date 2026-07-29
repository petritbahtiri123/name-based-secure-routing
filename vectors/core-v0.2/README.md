# NBSR Core v0.2 deterministic vectors

This package is test-only and must not be imported by runtime code.
Raw `.cbor`, `.cose`, and `.bin` files are authoritative.
Regenerate with `python scripts/generate_core_v02_vectors.py --write vectors/core-v0.2` and verify with `--check`.

The manifest uses closed enums and exact SHA-256/length assertions. Valid vectors contain no Origin Endpoint or IP literal. Test seeds are public and never production keys. These vectors make no production-readiness or cross-language claim until a second independent verifier passes.
