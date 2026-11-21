"""Offline package configuration contract; no runtime activation."""

import importlib.util
import json
from pathlib import Path
import socket
import subprocess

import pytest

ROOT = Path(__file__).resolve().parent


def implementation():
    path = ROOT / "validate_config.py"
    assert path.is_file(), "Stage 2 offline validator is not implemented"
    spec = importlib.util.spec_from_file_location("single_instance_config", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sample():
    return {
        "schema_version": "nbsr-single-instance-config-v1",
        "mode": "offline",
        "client": {
            "service_id": "11" * 32,
            "gateway_id": "gateway.fixture",
            "proxy": {"host": "127.0.0.1", "port": 18080},
            "identity_ref": "ref:client-identity",
        },
        "gateway": {
            "gateway_id": "gateway.fixture",
            "endpoint": {"host": "gateway.example.test", "port": 4433},
            "trust_ref": "ref:gateway-trust",
            "registration_policy_ref": "ref:registration-policy",
        },
        "origin": {
            "identity_ref": "ref:connector-identity",
            "services": [
                {
                    "service_id": "11" * 32,
                    "gateway_id": "gateway.fixture",
                    "operator_id": "33" * 32,
                    "connector_principal": "44" * 32,
                    "registration_authority_ref": "ref:registration-authority",
                    "target": {
                        "scheme": "http",
                        "host": "private-origin.example.test",
                        "port": 8080,
                        "method": "GET",
                        "path": "/",
                        "max_request_bytes": 4096,
                        "max_response_bytes": 4096,
                    },
                }
            ],
        },
        "registration": {
            "requested_lease_seconds": 60,
            "exchange_timeout_seconds": 5,
            "connect_attempts": 3,
            "backoff_seconds": [1, 2],
            "owners_per_service": 1,
            "pending_per_connection": 1,
            "completed_results_per_connection": 4,
            "waiting_registrations": 0,
        },
    }


def test_valid_config_is_not_readiness():
    result = implementation().validate_bytes(json.dumps(sample()).encode())
    assert result["status"] == "CONFIG_VALID_OFFLINE"
    assert result["ready"] is False
    assert result["references_verified"] is False
    assert result["service_count"] == 1
    assert "origin" not in json.dumps(result)


@pytest.mark.parametrize(
    "path,value",
    [
        (("schema_version",), "v2"),
        (("mode",), "pilot"),
        (("client", "identity_ref"), ""),
        (("client", "identity_ref"), "secret-inline"),
        (("gateway", "trust_ref"), "../trust.pem"),
        (("gateway", "registration_policy_ref"), None),
        (("client", "service_id"), "00" * 32),
        (("client", "gateway_id"), "55" * 32),
        (("client", "service_id"), "55" * 32),
        (("client", "proxy", "host"), "0.0.0.0"),
        (("gateway", "endpoint", "port"), True),
        (("gateway", "endpoint", "port"), "4433"),
        (("gateway", "endpoint", "port"), 0),
        (("gateway", "endpoint", "port"), 65536),
        (("gateway", "endpoint", "host"), "https://user:secret@example.test"),
        (("gateway", "endpoint", "host"), "EXAMPLE.test"),
        (("gateway", "endpoint", "host"), "0.0.0.0"),
        (("registration", "requested_lease_seconds"), 61),
        (("registration", "requested_lease_seconds"), 0),
        (("registration", "exchange_timeout_seconds"), 6),
        (("registration", "connect_attempts"), 4),
        (("registration", "backoff_seconds"), [0, 1]),
        (("registration", "waiting_registrations"), 1),
        (("registration", "completed_results_per_connection"), 5),
        (("origin", "services"), []),
        (("origin", "services"), [sample()["origin"]["services"][0]] * 2),
    ],
)
def test_invalid_fields(path, value):
    config = sample()
    node = config
    for key in path[:-1]:
        node = node[key]
    node[path[-1]] = value
    with pytest.raises(ValueError):
        implementation().validate_bytes(json.dumps(config).encode())


@pytest.mark.parametrize(
    "key,value",
    [
        ("scheme", "https"),
        ("method", "POST"),
        ("path", "/admin"),
        ("host", "http://10.0.0.1"),
        ("host", "169.254.169.254"),
        ("host", "8.8.8.8"),
        ("max_response_bytes", 4097),
    ],
)
def test_invalid_origin_profile(key, value):
    config = sample()
    config["origin"]["services"][0]["target"][key] = value
    with pytest.raises(ValueError):
        implementation().validate_bytes(json.dumps(config).encode())


@pytest.mark.parametrize("section", [None, "client", "gateway", "origin", "registration"])
def test_missing_and_unknown_keys(section):
    validator = implementation()
    config = sample()
    obj = config if section is None else config[section]
    obj["unexpected-secret-key"] = "DO-NOT-PRINT"
    with pytest.raises(ValueError) as error:
        validator.validate_bytes(json.dumps(config).encode())
    assert "DO-NOT-PRINT" not in str(error.value)
    assert "unexpected-secret-key" not in str(error.value)
    config = sample()
    obj = config if section is None else config[section]
    obj.pop(next(iter(obj)))
    with pytest.raises(ValueError):
        validator.validate_bytes(json.dumps(config).encode())


@pytest.mark.parametrize(
    "raw",
    [
        b'{"client":{},"client":{}}',
        b'{"client":{"x":1,"x":2}}',
        b"{}{}",
        b"{",
        b"[]",
        b"null",
        b'{"x":NaN}',
        b"\xff",
        b" " * 65537,
        b"[" * 1100 + b"]" * 1100,
    ],
    ids=["duplicate-root", "duplicate-nested", "trailing", "broken", "list", "null", "nan", "utf8", "large", "deep"],
)
def test_malformed_or_ambiguous_json(raw):
    with pytest.raises(ValueError):
        implementation().validate_bytes(raw)


def test_valid_example_and_schema_are_current():
    validator = implementation()
    assert json.loads((ROOT / "config.example.json").read_text()) == sample()
    assert validator.validate_bytes((ROOT / "config.example.json").read_bytes())["ready"] is False
    assert json.loads((ROOT / "config.schema.json").read_text()) == validator.configuration_schema()


def test_preflight_has_no_external_effects(monkeypatch, tmp_path, capsys):
    validator = implementation()
    path = tmp_path / "config.json"
    path.write_text(json.dumps(sample()))
    original_open = Path.open
    opened = []

    def read_config_only(self, mode="r", *args, **kwargs):
        assert self == path and mode == "rb"
        opened.append(self)
        return original_open(self, mode, *args, **kwargs)

    def forbidden(*args, **kwargs):
        pytest.fail("preflight attempted external effect")

    monkeypatch.setattr(Path, "open", read_config_only)
    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(Path, "mkdir", forbidden)
    monkeypatch.setenv("NBSR_GATEWAY_URL", "https://DO-NOT-USE")
    assert validator.main([str(path)]) == 0
    assert opened == [path]
    result = json.loads(capsys.readouterr().out)
    assert result["ready"] is False and result["references_verified"] is False


def test_cli_missing_input_is_redacted(tmp_path, capsys):
    assert implementation().main([str(tmp_path / "DO-NOT-PRINT")]) == 2
    error = capsys.readouterr().err
    assert "CONFIG_INVALID" in error and "unreadable" in error
    assert "DO-NOT-PRINT" not in error


def test_json_cli_valid_config(tmp_path, capsys):
    path = tmp_path / "config.json"
    path.write_text(json.dumps(sample()), encoding="utf-8")

    assert implementation().main(["--json", str(path)]) == 0
    output = capsys.readouterr()
    assert json.loads(output.out) == {
        "status": "CONFIG_VALID_OFFLINE",
        "ready": False,
        "references_verified": False,
        "service_count": 1,
    }
    assert output.err == ""


def test_json_cli_missing_required_field(tmp_path, capsys):
    config = sample()
    del config["client"]["identity_ref"]
    path = tmp_path / "config.json"
    path.write_text(json.dumps(config), encoding="utf-8")

    assert implementation().main(["--json", str(path)]) == 2
    output = capsys.readouterr()
    assert json.loads(output.out) == {
        "status": "CONFIG_INVALID",
        "field": "client.identity_ref",
        "reason": "missing",
    }
    assert output.err == ""


def test_json_cli_redacts_invalid_secret(tmp_path, capsys):
    config = sample()
    config["client"]["identity_ref"] = "DO-NOT-PRINT-SECRET"
    path = tmp_path / "config.json"
    path.write_text(json.dumps(config), encoding="utf-8")

    assert implementation().main(["--json", str(path)]) == 2
    output = capsys.readouterr()
    assert "DO-NOT-PRINT-SECRET" not in output.out + output.err
    result = json.loads(output.out)
    assert result["status"] == "CONFIG_INVALID"
    assert result["field"] == "client.identity_ref"
    assert result["reason"]
    assert output.err == ""


def test_diagnostic_identifies_known_field_without_value():
    config = sample()
    config["client"]["identity_ref"] = "DO-NOT-PRINT"
    with pytest.raises(ValueError) as error:
        implementation().validate_bytes(json.dumps(config).encode())
    assert "client.identity_ref" in str(error.value)
    assert "DO-NOT-PRINT" not in str(error.value)


@pytest.mark.parametrize(
    "field,value",
    [("owners_per_service", True), ("requested_lease_seconds", 1.0), ("pending_per_connection", False), ("backoff_seconds", [True, 2])],
)
def test_numeric_types_do_not_coerce(field, value):
    config = sample()
    config["registration"][field] = value
    with pytest.raises(ValueError):
        implementation().validate_bytes(json.dumps(config).encode())


def test_origin_scope_and_reference_required():
    validator = implementation()
    config = sample()
    config["origin"]["services"][0]["gateway_id"] = "55" * 32
    with pytest.raises(ValueError):
        validator.validate_bytes(json.dumps(config).encode())
    config = sample()
    del config["origin"]["services"][0]["registration_authority_ref"]
    with pytest.raises(ValueError):
        validator.validate_bytes(json.dumps(config).encode())


def test_schema_backoff_matches_approved_profile():
    schema = implementation().configuration_schema()
    assert schema["$defs"]["Registration"]["properties"]["backoff_seconds"]["const"] == [1, 2]


def test_cli_import_and_check_audit_no_effects(tmp_path):
    import os
    import sys

    config = tmp_path / "offline.json"
    config.write_text(json.dumps(sample()))
    probe = r"""
import sys, runpy
sys.dont_write_bytecode = True
config, script = sys.argv[1:]
def guard(event, args):
    if event.startswith(('socket.', 'subprocess.')) or event in ('os.system','os.mkdir','os.remove','os.rename'):
        raise AssertionError('unexpected external effect: ' + event)
    if event == 'open':
        mode, flags = args[1], args[2]
        if (isinstance(mode,str) and any(x in mode for x in 'wax+')) or (isinstance(flags,int) and flags & (1|2|64|512|1024)):
            raise AssertionError('unexpected write')
sys.addaudithook(guard)
sys.argv = [script, config]
runpy.run_path(script, run_name='__main__')
"""
    result = subprocess.run(
        [sys.executable, "-B", "-c", probe, str(config), str(ROOT / "validate_config.py")],
        capture_output=True,
        text=True,
        timeout=15,
        env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"),
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["ready"] is False


def test_oversized_integer_is_redacted_cli_failure(tmp_path, capsys):
    path = tmp_path / "integer.json"
    path.write_bytes(b'{"x":' + b"9" * 5000 + b"}")
    assert implementation().main([str(path)]) == 2
    error = capsys.readouterr().err
    assert "CONFIG_INVALID" in error and "9999999" not in error


@pytest.mark.parametrize(
    "mode,attributes",
    [(0o120777, 0), (0o040755, 0x400), (0o040755, 0x1000),
     (0o040755, 0x40000), (0o040755, 0x400000)],
    ids=["symlink", "reparse", "offline", "recall-on-open", "recall-on-data"],
)
def test_unsafe_parent_rejected_before_descendant_access(mode, attributes, monkeypatch, tmp_path, capsys):
    from types import SimpleNamespace

    validator = implementation()
    original = Path.lstat
    visited = []
    child = tmp_path / "remote-link" / "config.json"
    link = child.parent

    def inspect(self, *args, **kwargs):
        visited.append(self)
        if self == link:
            return SimpleNamespace(st_mode=mode, st_file_attributes=attributes)
        assert self != child, "must not traverse an untrusted reparse parent"
        return original(self, *args, **kwargs)

    def no_open(*args, **kwargs):
        pytest.fail("opened input before rejecting link")

    monkeypatch.setattr(Path, "lstat", inspect)
    monkeypatch.setattr(Path, "open", no_open)
    assert validator.main([str(child)]) == 2
    assert link in visited
    assert "local" in capsys.readouterr().err


def test_example_gateway_id_passes_actual_registration_body_contract():
    from nbsr.connector_registration_offline import canonical, decode_body

    config = json.loads((ROOT / "config.example.json").read_text())
    assert implementation().validate_bytes(json.dumps(config).encode())["ready"] is False
    request_path = ROOT.parents[1] / "vectors/connector-registration-v1-counter/request.cbor"
    body = decode_body("REQUEST", request_path.read_bytes())
    for gateway_id in (config["client"]["gateway_id"], config["gateway"]["gateway_id"], config["origin"]["services"][0]["gateway_id"]):
        body[6] = gateway_id
        assert decode_body("REQUEST", canonical(body))[6] == gateway_id


@pytest.mark.parametrize("gateway_id", ["a", "gateway.fixture", "a" * 64, "a-1.b_2"])
def test_gateway_text64_preserved_across_config_and_request(gateway_id):
    from nbsr.connector_registration_offline import canonical, decode_body

    config = sample()
    for item in (config["client"], config["gateway"], config["origin"]["services"][0]):
        item["gateway_id"] = gateway_id
    validator = implementation()
    assert validator.validate_bytes(json.dumps(config).encode())["ready"] is False
    parsed = validator.Configuration.model_validate(config)
    assert parsed.gateway.gateway_id == gateway_id
    body = decode_body("REQUEST", (ROOT.parents[1] / "vectors/connector-registration-v1-counter/request.cbor").read_bytes())
    body[6] = parsed.gateway.gateway_id
    assert decode_body("REQUEST", canonical(body))[6] == gateway_id


@pytest.mark.parametrize("gateway_id", ["", "a" * 65, "22" * 32, "Gateway", "a..b", "a-", "a\n", " g", "g ", "g\u00e9", 1])
@pytest.mark.parametrize("role", ["client", "gateway", "service"])
def test_invalid_gateway_text64_rejected_at_each_role(gateway_id, role):
    config = sample()
    node = config["origin"]["services"][0] if role == "service" else config[role]
    node["gateway_id"] = gateway_id
    with pytest.raises(ValueError):
        implementation().validate_bytes(json.dumps(config).encode())


def test_valid_text_gateway_mismatch_rejects():
    config = sample()
    config["client"]["gateway_id"] = "gateway.other"
    with pytest.raises(ValueError):
        implementation().validate_bytes(json.dumps(config).encode())


@pytest.mark.parametrize(
    "path,value",
    [
        (("client", "identity_ref"), "ref:substituted-client"),
        (("origin", "identity_ref"), "ref:substituted-origin"),
        (("gateway", "trust_ref"), "ref:substituted-trust"),
        (("gateway", "registration_policy_ref"), "ref:substituted-policy"),
        (("origin", "services", 0, "registration_authority_ref"), "ref:substituted-authority"),
        (("origin", "services", 0, "connector_principal"), "55" * 32),
        (("origin", "services", 0, "operator_id"), "66" * 32),
    ],
)
def test_well_formed_identity_substitution_never_verifies_authority(path, value):
    data = sample()
    target = data
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    result = implementation().validate_bytes(json.dumps(data).encode())
    assert result == {"status": "CONFIG_VALID_OFFLINE", "ready": False, "references_verified": False, "service_count": 1}


@pytest.mark.parametrize(
    "path,value",
    [
        (("client", "service_id"), "77" * 32),
        (("origin", "services", 0, "service_id"), "77" * 32),
        (("client", "gateway_id"), "other.fixture"),
        (("origin", "services", 0, "gateway_id"), "other.fixture"),
    ],
)
def test_cross_role_identity_substitution_is_rejected(path, value):
    data = sample()
    target = data
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    validator = implementation()
    with pytest.raises(validator.ConfigError):
        validator.validate_bytes(json.dumps(data).encode())


@pytest.mark.parametrize(
    "host",
    [
        "10.0.0.0", "10.255.255.255", "172.16.0.0", "172.31.255.255",
        "192.168.0.0", "192.168.255.255", "127.0.0.1", "::1",
        "fc00::", "fdff:ffff:ffff:ffff:ffff:ffff:ffff:ffff",
    ],
)
def test_origin_private_literal_boundaries_remain_offline_only(host):
    config = sample()
    config["origin"]["services"][0]["target"]["host"] = host
    validator = implementation()
    assert validator.validate_bytes(json.dumps(config).encode()) == {
        "status": "CONFIG_VALID_OFFLINE", "ready": False,
        "references_verified": False, "service_count": 1,
    }
    assert validator.Configuration.model_validate(config).origin.services[0].target.host == host


@pytest.mark.parametrize(
    "host",
    [
        "9.255.255.255", "11.0.0.0", "172.15.255.255", "172.32.0.0",
        "192.167.255.255", "192.169.0.0", "126.255.255.255", "128.0.0.0",
        "fbff:ffff:ffff:ffff:ffff:ffff:ffff:ffff", "fe00::", "::2",
    ],
)
def test_origin_literals_outside_approved_networks_rejected(host):
    config = sample()
    config["origin"]["services"][0]["target"]["host"] = host
    validator = implementation()
    with pytest.raises(validator.ConfigError):
        validator.validate_bytes(json.dumps(config).encode())


@pytest.mark.parametrize("host", ["FD00::1", "fd00:0:0:0:0:0:0:1", "fd00::1%eth0", "[::1]", "::", "fe80::1", "ff02::1"])
@pytest.mark.parametrize("role", ["gateway", "origin"])
def test_noncanonical_or_unsafe_ipv6_rejected_at_both_endpoint_roles(host, role):
    config = sample()
    endpoint = config["gateway"]["endpoint"] if role == "gateway" else config["origin"]["services"][0]["target"]
    endpoint["host"] = host
    validator = implementation()
    with pytest.raises(validator.ConfigError):
        validator.validate_bytes(json.dumps(config).encode())


@pytest.mark.parametrize(
    "mode,attributes",
    [
        (0o040755, 0),
        (0o120777, 0),
        (0o100644, 0x400),
        (0o100644, 0x1000),
        (0o100644, 0x40000),
        (0o100644, 0x400000),
    ],
    ids=["directory", "symlink", "reparse", "offline", "recall-on-open", "recall-on-data"],
)
def test_unmaterialized_or_nonregular_leaf_rejected_before_open(
    mode, attributes, monkeypatch, tmp_path, capsys
):
    from types import SimpleNamespace

    validator = implementation()
    path = tmp_path / "DO-NOT-PRINT.json"
    original_lstat = Path.lstat
    inspected = []

    def inspect(self, *args, **kwargs):
        if self == path:
            inspected.append(self)
            return SimpleNamespace(st_mode=mode, st_file_attributes=attributes)
        return original_lstat(self, *args, **kwargs)

    def forbidden_open(*args, **kwargs):
        pytest.fail("opened rejected configuration input")

    monkeypatch.setattr(Path, "lstat", inspect)
    monkeypatch.setattr(Path, "open", forbidden_open)
    assert validator.main([str(path)]) == 2
    assert inspected == [path]
    output = capsys.readouterr()
    assert output.out == ""
    assert "CONFIG_INVALID" in output.err
    assert "DO-NOT-PRINT" not in output.err


@pytest.mark.parametrize("name", ["//server/share/secret.json", r"\\server\share\secret.json"])
def test_network_input_rejected_before_filesystem_inspection(name, monkeypatch, capsys):
    validator = implementation()

    def forbidden(*args, **kwargs):
        pytest.fail("inspected or opened network configuration input")

    monkeypatch.setattr(Path, "lstat", forbidden)
    monkeypatch.setattr(Path, "open", forbidden)
    assert validator.main([name]) == 2
    output = capsys.readouterr()
    assert output.out == ""
    assert "CONFIG_INVALID" in output.err
    assert "secret" not in output.err

