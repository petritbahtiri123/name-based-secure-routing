# WP4 public documentation alignment design

**Date:** 2026-08-01
**Status:** Approved design; implementation pending

## Goal

Align the public documentation added by the latest remote merge with the completed WP4 reusable multi-service transport laboratory scope. The update must remain evidence-based and must not expand the implemented or security boundary.

## Scope

Update:

- `docs/project-history.md` with a concise WP4 history section;
- `SECURITY.md` with the WP4 security-sensitive surfaces now supported for vulnerability reporting;
- `CONTRIBUTING.md` with validation guidance for locked Rust dependencies and applicable Core/WP4 vector checks;
- focused documentation tests that prevent these statements from drifting.

Do not update the GitHub issue or pull-request templates because their existing language is generic and remains accurate.

## WP4 claims to record

The history may describe only the completed origin-free, same-edge, reusable multi-service loopback laboratory slice:

- up to 32 isolated Service Channels per Transport Session;
- up to 64 reliable streams per channel;
- fresh RouteGrant and nonce admission for every additional channel;
- TLS exporter binding over canonical channel context with independent Python, Node.js, and Rust vectors;
- bounded TCP and UDP behavior, per-service authorization, revocation, quotas, audit, and failure containment;
- bounded drain and same-edge resume authority.

## Required non-claims

The update must continue to deny production readiness, OriginSet selection, Origin Endpoint connection or forwarding, NameRelay integration, cross-edge resume, 0-RTT, global federation, and complete runtime interoperability. It must not imply frozen Core v0.1 registry, schema, state-machine, or wrapper changes.

## Validation and delivery

Add documentation regressions before editing the public documents, verify the focused tests fail, then make them pass. Run focused documentation/protocol tests, the full Python suite, Ruff, Rust tests/format/Clippy, vector regeneration and independent Node verification, `pip check`, and `git diff --check` as applicable. Commit the public alignment separately and push only `codex/nbsr-v3-wp0-wp1`.
