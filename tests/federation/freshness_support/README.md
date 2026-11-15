# Freshness support: fixture-only integration proposal

Single canonical test-support package for the owned memory pipeline, currentness
barrier and lifetime manager. No production authority, directory verifier, physical
backend or new trust anchor. Keep these modules outside runtime packages.

The adjacent token lineage/failure tests import this package. Support modules use
relative imports; no absolute task paths, environment source selection or sys.path
mutation. fixture_setup reuses the existing test_inclusion_persistence.initialized
and store helpers, rather than duplicating the existing memory snapshot backend.
This test-to-test helper dependency is explicit; a future extraction should move
the existing helper and all consumers together, not copy it into another backend.

Run from repository root with the provisioned supported environment:

    python -B -m pytest -q -p no:cacheprovider tests/federation/test_token_refresh_lineage.py tests/federation/test_issued_token_failure.py

Use the existing pyproject Python range and constraints/dev.txt; at the proposal
base pytest=8.4.2, cryptography=45.0.7 and cbor2=5.9.0. Full existing constraints
remain authoritative. No installation or dependency change is made by this patch.
The inclusion fixture also requires existing scripts/nbsr sources, registries and
public vectors; sparse omissions must not be silently repaired by the tests.

CI should use an immutable reviewed checkout, ordinary pytest prepend import mode,
and a provisioned environment with untrusted PYTHONPATH/PYTEST_ADDOPTS/plugin
configuration excluded by its launcher. No security setting or global environment
change is performed by this support package. No dependency download fallback.

This patch adds six lifecycle tests, not the standalone runner's five packaging
tests. The per-run manifest runner remains isolated review tooling, not duplicated
in repository CI. Preserve its historical evidence. These tests prove synchronous
memory-fixture behavior only; no successful new-manager recovery, physical writer
lease, runtime READY, production provenance or power-loss durability is claimed.

Before integration, authority/freshness owners must agree on ownership of these
canonical files and retire parallel implementation copies from active imports.
Historical task artifacts may remain as evidence but must not become another CI
implementation. No broad CI-profile selection or readiness update is implied.
