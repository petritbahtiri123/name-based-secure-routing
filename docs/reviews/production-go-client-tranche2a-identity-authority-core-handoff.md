# Tranche 2A identity/authority core — closure handoff

## Immutable reference set

| Record | SHA / path |
| --- | --- |
| Approved plan baseline | `0b15dc3a54698854badec99dd55d2ff051c68e82` — `docs/superpowers/plans/2026-08-14-production-go-client-tranche2a-identity-authority-core.md` |
| Final Tranche 2A implementation baseline | `530e19e4001a13e601d60405085e48709b9a3bbf` |
| GREEN closure evidence commit | `900735078c514d50a690e23ec1242db2b922d981` — `docs/reviews/production-go-client-tranche2a-identity-authority-core.md` |
| Retained RED evidence commit | `785ed81768d87414a67b9287dba852a53fed5746` — `docs/reviews/production-go-client-tranche2a-identity-authority-core-red-evidence.md` |
| Protected local and remote `main` | `1938154d498b32d81a3564319969430644e8a688` |

## Evidence reading order

1. Read the approved plan baseline for bounded Tranche 2A scope.
2. Read the retained RED evidence for the pre-execution all-FAIL template,
   exact RED command, observed exit code, and its explicit non-immutability
   limitation.
3. Read the GREEN closure evidence for direct acceptance-command results,
   changed-path audit, benchmark nonclaims, protected diff, and exclusions.
4. Treat the final implementation baseline as the source state immediately
   before the closure-evidence packaging commit.

## Handoff packaging rule

This handoff commit is the final packaging commit reported externally. Its own
SHA cannot be embedded here without changing the commit and producing a new
SHA, so the externally reported handoff SHA is authoritative for this document.
This avoids an impossible self-referential commit-hash claim. No production
code, protocol authority, protected path, or `main` ref is changed by this
handoff.

## Scope and non-claims

The record preserves local package/test evidence only. It does not claim live
ACP/HTTP transport, wire interoperability, enrollment, resolver/platform/TPM
work, WAN/demo readiness, performance capacity, or production readiness. The
Tranche 2B and later exclusions in the GREEN closure remain in force.
