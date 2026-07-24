from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "deploy" / "kind" / "nbsr.yaml"
PINNED_NODE_IMAGE = (
    "kindest/node:v1.35.0@sha256:"
    "452d707d4862f52530247495d180205e029056831160e22870e37e3f6c1ac31f"
)


def _document(name: str) -> str:
    for document in MANIFEST.read_text(encoding="utf-8").split("\n---\n"):
        if f"name: {name}," in document or f"name: {name}\n" in document:
            return document
    raise AssertionError(f"missing Kubernetes document {name!r}")


def test_kind_manifest_has_no_namespace_wide_egress_escape_hatch():
    manifest = MANIFEST.read_text(encoding="utf-8")

    assert "allow-required-flows" not in manifest
    assert "namespaceSelector: {}" not in manifest


def test_kind_manifest_allows_only_named_workload_flows():
    expected_policies = {
        "opa-from-control-plane",
        "control-plane-public-ingress",
        "control-plane-to-opa",
        "ticket-verifier-from-gateway",
        "payments-from-gateway-only",
        "gateway-public-ingress",
        "gateway-to-backends",
        "name-origin-from-relay-only",
        "name-control-ingress",
        "name-relay-ingress",
        "name-relay-to-origin",
        "dns-egress",
    }

    for policy in expected_policies:
        assert f"name: {policy}," in _document(policy)

    assert "app: control-plane" in _document("opa-from-control-plane")
    assert "port: 8181" in _document("opa-from-control-plane")
    assert "app: gateway" in _document("ticket-verifier-from-gateway")
    assert "port: 9000" in _document("ticket-verifier-from-gateway")
    assert "app: gateway" in _document("payments-from-gateway-only")
    assert "port: 7000" in _document("payments-from-gateway-only")
    assert "app: name-relay" in _document("name-origin-from-relay-only")
    assert "port: 443" in _document("name-origin-from-relay-only")


def test_kind_enterprise_ingress_uses_generated_tls_material():
    control_plane = _document("control-plane")
    gateway = _document("gateway")

    assert "--ssl-certfile" in control_plane
    assert "/run/nbsr-tls/enterprise-control-plane-cert.pem" in control_plane
    assert "secretName: nbsr-enterprise-tls" in control_plane
    assert "enterprise-gateway-cert.pem" in gateway
    assert "enterprise-gateway-key.pem" in gateway
    assert "secretName: nbsr-enterprise-tls" in gateway


def test_kind_bootstrap_pins_node_image_and_runs_network_policy_probe():
    for script_name in ("kind-up.ps1", "kind-up.sh"):
        script = (ROOT / "scripts" / script_name).read_text(encoding="utf-8")
        assert PINNED_NODE_IMAGE in script
        assert "--image" in script
        assert "verify-kind-security" in script


def test_kind_security_probe_covers_allowed_and_denied_paths():
    powershell = (ROOT / "scripts" / "verify-kind-security.ps1").read_text(encoding="utf-8")
    shell = (ROOT / "scripts" / "verify-kind-security.sh").read_text(encoding="utf-8")

    for script in (powershell, shell):
        assert "control-plane" in script
        assert "opa" in script
        assert "8181" in script
        assert "payments-service" in script
        assert "7000" in script
        assert "name-relay" in script
        assert "test" in script
        assert "443" in script
        assert "restartCount" in script
