from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_compose_publishes_only_required_loopback_ports():
    compose = (ROOT / "compose.yaml").read_text(encoding="utf-8")

    for mapping in ("8000:8000", "8080:8080", "8443:8443", "8444:8444"):
        assert f"127.0.0.1:{mapping}" in compose
        assert f'"{mapping}"' not in compose
    assert "0.0.0.0:" not in "\n".join(line for line in compose.splitlines() if "ports:" in line)


def test_compose_separates_enterprise_and_isp_trust_boundaries():
    compose = (ROOT / "compose.yaml").read_text(encoding="utf-8")

    assert "enterprise-client-network" in compose
    assert "enterprise-control-network" in compose
    assert "enterprise-protected-network" in compose
    assert "isp-client-network" in compose
    assert "isp-origin-network" in compose
    relay_block = compose.split("  name-relay:", 1)[1].split("\n  client-allowed:", 1)[0]
    payments_block = compose.split("  payments-service:", 1)[1].split("\n  gateway:", 1)[0]
    assert "enterprise-protected-network" not in relay_block
    assert "payments-service" not in relay_block
    assert "isp-origin-network" in relay_block
    assert "ports:" not in payments_block


def test_internal_enterprise_hops_are_mutual_tls_only():
    compose = (ROOT / "compose.yaml").read_text(encoding="utf-8")
    envoy = (ROOT / "gateway" / "envoy.yaml").read_text(encoding="utf-8")

    assert "NBSR_OPA_URL: https://opa:8181/" in compose
    assert "--authentication=tls" in compose
    assert "--tls-ca-cert-file=/run/nbsr-tls/demo-ca.pem" in compose
    for service, next_service in (("ticket-verifier", "payments-service"), ("payments-service", "gateway")):
        block = compose.split(f"  {service}:", 1)[1].split(f"\n  {next_service}:", 1)[0]
        assert "--ssl-ca-certs" in block
        assert "--ssl-cert-reqs" in block
    assert "http://ticket-verifier" not in envoy
    assert "https://ticket-verifier:9000" in envoy
    assert envoy.count("UpstreamTlsContext") == 2
    assert "enterprise-gateway-client-cert.pem" in envoy
    assert "match_typed_subject_alt_names" in envoy
    assert "ticket-verifier" in envoy
    assert "payments-service" in envoy


def test_kind_host_mappings_are_loopback_only():
    cluster = (ROOT / "deploy" / "kind" / "cluster.yaml").read_text(encoding="utf-8")

    assert cluster.count('listenAddress: "127.0.0.1"') == 3


def test_gateway_default_is_https():
    config = (ROOT / "nbsr" / "config.py").read_text(encoding="utf-8")

    assert 'gateway_url: str = "https://localhost:8080"' in config
