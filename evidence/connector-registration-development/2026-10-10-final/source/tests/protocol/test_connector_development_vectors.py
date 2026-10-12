"""Development allocation and retained-package checks; no live authority."""

import json
from hashlib import sha256

from scripts.generate_connector_development_vectors import ALPN, PACKAGE, PROFILE, REGISTRY, artifacts


def test_development_registry_has_only_approved_local_effects():
    registry = json.loads(REGISTRY.read_text())
    assert registry["profile"] == PROFILE == "connector-registration-development-v1"
    assert registry["alpn"] == ALPN == "nbsr-connector-dev-1"
    assert registry["envelope_version"] == 1
    assert registry["runtime_authorized"] is False
    assert registry["live_trust_authorized"] is False
    assert registry["messages"] == dict(zip(("REQUEST", "CHALLENGE", "PROOF", "ACCEPT", "REJECT", "WITHDRAW"), range(24576, 24582)))
    assert registry["actions"]["namespace"] == PROFILE
    assert registry["actions"]["CONNECTOR_REGISTER"] == 24576
    assert registry["actions"]["effects"] == ["register", "renew"]
    assert registry["signer_purposes"] == {"transport": 14, "delegation": 6, "bilateral_authorization": 11}


def test_retained_development_package_is_reproducible():
    registry, files = artifacts()
    assert json.loads(REGISTRY.read_text()) == registry
    assert {p.name for p in PACKAGE.iterdir() if p.is_file()} == set(files)
    for name, raw in files.items():
        assert (PACKAGE / name).read_bytes() == raw, name


def test_shared_manifest_authenticates_every_vector_byte():
    manifest = json.loads((PACKAGE / "manifest.json").read_text())
    assert len(manifest["cases"]) == 25
    assert sum(c["accepted"] for c in manifest["cases"]) == 6
    assert {c["file"] for c in manifest["cases"]} == set(manifest["artifacts"])
    for name, expected in manifest["artifacts"].items():
        raw = (PACKAGE / name).read_bytes()
        assert len(raw) == expected["bytes"]
        assert sha256(raw).hexdigest() == expected["sha256"]
