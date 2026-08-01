# Contributing to NBSR

Thank you for helping improve Name-Based Secure Routing (NBSR).

NBSR is an experimental open protocol and reference implementation. Contributions must preserve its security boundaries, deterministic protocol behavior, interoperability goals, and explicit non-production claims.

## Before contributing

- Read `README.md`, `docs/protocol/status.md`, and the authoritative architecture documents.
- Do not treat planned or normative behavior as implemented.
- Open an issue before making a large protocol, wire-format, registry, cryptographic, trust-model, or compatibility change.
- Do not submit credentials, private keys, tokens, production logs, personal data, or confidential third-party material.

## Development workflow

1. Create a focused branch from the active development branch.
2. Keep each change narrow and reviewable.
3. Add or update tests for behavioral changes.
4. Update protocol documentation when semantics, schemas, states, registries, security boundaries, or non-claims change.
5. Run the applicable checks before opening a pull request.

Primary checks:

```bash
python -m pytest -q
python -m ruff check .
python -m ruff format --check .
python -m pip check
cargo fmt --manifest-path crates/nbsr-transport/Cargo.toml --check
cargo clippy --manifest-path crates/nbsr-transport/Cargo.toml --all-targets -- -D warnings
cargo test --manifest-path crates/nbsr-transport/Cargo.toml
```

Run OPA, Compose, Kind, vector-regeneration, and packaging checks when the affected area requires them.

## Protocol change requirements

Protocol changes must identify:

- the problem being solved;
- the affected trust boundary;
- wire compatibility and downgrade behavior;
- resource and timeout bounds;
- replay, revocation, rollback, and failure behavior;
- privacy and metadata impact;
- migration implications;
- tests and deterministic vectors required;
- documentation and conformance impact.

Security-sensitive parsing and verification must fail closed. Avoid generic command execution, caller-trusted network destinations, implicit fallback, unbounded state, or ambiguous encodings.

## Pull requests

A pull request should include:

- what changed and why;
- the affected work package or protocol boundary;
- user, operator, and security impact;
- tests performed and their results;
- limitations or unresolved decisions;
- confirmation that no secrets or confidential data were included.

## Developer Certificate of Origin

NBSR uses the Developer Certificate of Origin 1.1. Sign off each commit using:

```bash
git commit -s -m "Describe the change"
```

The sign-off certifies that you have the right to submit the contribution under the project license. The DCO text is available at <https://developercertificate.org/>.

## Licensing

Unless explicitly stated otherwise, contributions intentionally submitted for inclusion in this repository are provided under the Apache License 2.0, consistent with the repository `LICENSE` file.

## Security reports

Do not disclose suspected vulnerabilities in public issues. Follow `SECURITY.md` instead.
