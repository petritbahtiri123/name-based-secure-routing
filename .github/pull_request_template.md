## Summary

Describe what changed and why.

## Scope

- Work package or component:
- Protocol, runtime, documentation, deployment, or tooling boundary:
- Explicitly out of scope:

## Security and compatibility impact

- Trust boundaries affected:
- Wire-format, registry, schema, or state changes:
- Downgrade and failure behavior:
- Replay, revocation, rollback, privacy, or resource-bound impact:
- Migration or interoperability impact:

## Validation

List exact commands and results.

```text
python -m pytest -q
python -m ruff check .
python -m ruff format --check .
```

Add Rust, OPA, Compose, Kind, vector-regeneration, packaging, or other checks when applicable.

## Documentation

- [ ] Documentation matches the implementation.
- [ ] `docs/protocol/status.md` remains evidence-based.
- [ ] Planned behavior is not presented as implemented.
- [ ] Non-production and non-conformance claims remain accurate.

## Submission checks

- [ ] The change is focused and reviewable.
- [ ] Tests cover new or changed behavior.
- [ ] Security-sensitive behavior fails closed.
- [ ] No credentials, private keys, tokens, production logs, personal data, or confidential material are included.
- [ ] Commits are signed off under the Developer Certificate of Origin.
- [ ] The contribution is submitted under Apache License 2.0.
