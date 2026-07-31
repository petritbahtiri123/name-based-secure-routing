# Task 4 report: Service Channel exporter vectors

## Status

Complete. The Core v0.2 Service Channel context and fixture-secret TLS 1.3
exporter derivation are frozen with independently implemented Python, Node.js,
and Rust agreement. No live rustls/Quinn exporter call was added.

## RED evidence

### Python RED

Command:

```powershell
python -m pytest tests/test_wp4_exporter_vectors.py -q
```

Observed before the generator or package existed: `2 failed`. The first test
failed because `scripts/generate_wp4_exporter_vectors.py` did not exist; the
second failed because the checked-in manifest did not exist. These were the
expected missing-feature failures.

### Rust RED

Command (with the required non-OneDrive target):

```powershell
$env:CARGO_TARGET_DIR='C:\Users\bajra\.codex\visualizations\2026\07\31\019fba00-bb69-7dc3-91b0-f91b72f33dd8\wp4-cargo-target'
& "$env:USERPROFILE\.cargo\bin\cargo.exe" test --locked --manifest-path crates/nbsr-transport/Cargo.toml --test exporter_vectors
```

Observed before the Rust implementation: compilation failed with unresolved
imports for `ServiceChannelContext`, `ServiceChannelExporterError`,
`canonical_service_channel_context`, and
`derive_service_channel_exporter_fixture`. This was the expected missing-API
failure.

## GREEN evidence

- Python independently encodes the canonical context, computes both RFC 8446
  HKDF steps with stdlib `hashlib`/`hmac`, verifies every artifact digest, and
  checks generator immutability: `2 passed`.
- Generator `--check` regenerated into a temporary directory and byte-compared
  the complete package without rewriting it: current.
- Node.js independently validates the closed schema, relative paths, artifact
  digests, bounded preferred CBOR, both HKDF steps, all declared rejections,
  and separation cases: `2 valid`, `21 invalid/mutation` verified.
- Rust consumes checked-in context/master-secret/output artifacts, matches both
  valid vectors exactly, proves a one-field mutation separates the binding,
  rejects an invalid context before derivation, and verifies redacted binding
  debug output: `3 passed`.

## Vector counts

- Valid vectors: 2 (one TCP, one UDP; different fixed 32-byte exporter master
  secrets and complete 14-item contexts).
- Invalid/mutation cases: 21.
- Mutation coverage: all 14 context-array items plus array reordering, wrong
  CBOR type, wrong fixed length, non-canonical CBOR, wrong label, wrong output
  length, and different master secret.
- Package files: 32 (manifest, 10 valid-vector artifacts, 21 invalid/mutation
  artifacts).

## Commands and results

```text
python -m pytest tests/test_wp4_exporter_vectors.py -q
  PASS: 2 passed

python scripts/generate_wp4_exporter_vectors.py --check
  PASS: 2 valid, 21 invalid/mutation; package byte-current

node scripts/verify_wp4_exporter_vectors.mjs vectors/core-v0.2/wp4-exporter
  PASS: verified 2 valid and 21 invalid/mutation cases

cargo test --locked --manifest-path crates/nbsr-transport/Cargo.toml --test exporter_vectors
  PASS: 3 passed

cargo test --locked --manifest-path crates/nbsr-transport/Cargo.toml --test core_v02_vectors --test multi_channel --test multi_stream --test application_stream --test exporter_vectors
  PASS: 15 passed

cargo fmt --manifest-path crates/nbsr-transport/Cargo.toml -- --check
  PASS

cargo clippy --locked --manifest-path crates/nbsr-transport/Cargo.toml --all-targets -- -D warnings
  PASS

git diff --check
  PASS
```

All Cargo commands used:
`C:\Users\bajra\.codex\visualizations\2026\07\31\019fba00-bb69-7dc3-91b0-f91b72f33dd8\wp4-cargo-target`.

## Files

- Added `docs/protocol/core-v0.2-service-channel-exporter.md`.
- Added `scripts/generate_wp4_exporter_vectors.py`.
- Added `scripts/verify_wp4_exporter_vectors.mjs`.
- Added `tests/test_wp4_exporter_vectors.py`.
- Added `vectors/core-v0.2/wp4-exporter/manifest.json` and its 31 referenced
  binary/text artifacts.
- Added `crates/nbsr-transport/src/channel_binding.rs`.
- Added `crates/nbsr-transport/tests/exporter_vectors.rs`.
- Modified `crates/nbsr-transport/src/lib.rs` only to export the narrow pure
  conformance context/derivation API.
- Added this report.

## Self-review

- The manifest schema and nested object schemas are exact-key/closed in both
  independent consumers; artifact paths are relative, traversal-safe, and
  digest/length checked.
- The generator and verifier share no imports or dependencies. Python uses only
  stdlib crypto; Node uses only built-in `crypto`; Rust uses existing `sha2`
  and a local HMAC/HKDF implementation. `Cargo.toml` and lockfiles are
  unchanged.
- Context validation precedes derivation. Rust retains no supplied exporter
  master secret and the returned binding has a redacted `Debug`; the context
  type has no `Debug` implementation.
- The Rust entry point is explicitly fixture-scoped and has no rustls/Quinn
  access. Admission, streams, origin, lifecycle, resume, UDP runtime behavior,
  Core v0.1, and existing Core v0.2 fixtures are unchanged.

## Commit

Planned commit: `feat(wp4): freeze service channel exporter vectors`.
The immutable Git object ID is recorded by the task handoff after this report
is included in that commit.

## Concerns

- This is conformance-only derivation from explicit fixture secrets. It is not
  evidence of a live TLS 1.3 handshake exporter or production channel binding;
  live rustls/Quinn exporter access remains Task 5.
