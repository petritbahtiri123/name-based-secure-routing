import importlib.util
from pathlib import Path
import tempfile
import unittest

SPEC = importlib.util.spec_from_file_location("isp_supervisor", Path(__file__).with_name("supervisor.py"))
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class SupervisorTests(unittest.TestCase):
    def test_failure_diagnostic_reports_trusted_origin_without_secret_values(self):
        secret = "PRIVATE_KEY_credential_192.0.2.99"
        with tempfile.TemporaryDirectory(prefix=secret) as temporary:
            path = Path(temporary) / (secret + ".json")
            path.write_text('{"' + secret + '":')
            try:
                MODULE.read_json(path)
            except Exception as error:
                diagnostic = MODULE.failure_diagnostic(error)
            else:
                self.fail("invalid JSON must fail")
        self.assertNotIn(secret, str(diagnostic))
        self.assertEqual(diagnostic["exception_type"], "JSONDecodeError")
        self.assertEqual(diagnostic["location"]["file"], "supervisor.py")
        self.assertEqual(diagnostic["location"]["function"], "read_json")
        self.assertGreater(diagnostic["location"]["line"], 0)
        self.assertEqual(set(diagnostic), {"status", "exception_type", "location"})

    def test_endpoint_only_projection_preserves_every_other_field(self):
        original = {
            "alpn": "nbsr-quic-1",
            "ca_der": "/r/ca.der",
            "client_cert_der": "/r/source.der",
            "client_key_der": "/r/source-key.der",
            "endpoint": "127.0.0.1:45979",
            "quic_version": "v1",
            "server_name": "destination.edge",
            "tls_version": "1.3",
        }
        changed = MODULE.transport_copy(original)
        self.assertEqual(changed.pop("endpoint"), "isp-b-adapter:45980")
        self.assertEqual(changed, {key: value for key, value in original.items() if key != "endpoint"})
        with self.assertRaises(ValueError):
            MODULE.transport_copy({**original, "fallback": "x"})
        with self.assertRaises(ValueError):
            MODULE.transport_copy({**original, "alpn": "other"})
        with self.assertRaises(ValueError):
            MODULE.transport_copy({**original, "endpoint": "192.0.2.1:45979"})

    def test_adapter_projection_never_contains_secrets(self):
        ready = {"Schema": "nbsr-demo-client-ready-v1", "Proxy": "127.0.0.1:54321", "SyntheticIP": "127.0.0.2", "State": "ready"}
        projected = MODULE.tcp_projection(ready)
        self.assertEqual(set(projected), {"schema", "transport", "upstream"})
        self.assertEqual(projected["upstream"], ready["Proxy"])
        with self.assertRaises(ValueError):
            MODULE.tcp_projection({**ready, "State": "failed"})

    def test_preflight_gate_requires_zero_allocations_and_retained_fixture_buckets(self):
        valid = {
            "schema": "nbsr-isp-preflight-v1",
            "status": "PASS",
            "source_sha": "a" * 40,
            "operators": ["isp-a", "isp-b"],
            "admitted_grants": 1,
            "active_allocations": 0,
            "limit_buckets": 8,
            "artifacts": {"x": "b" * 64},
            "live_runtime_federation": "NOT_CLAIMED",
        }
        MODULE.validate_preflight(valid, "a" * 40, {"x": "b" * 64})
        for change in ({"status": "FAIL"}, {"active_allocations": 1}, {"artifacts": {"x": "c" * 64}}, {"extra": 0}):
            with self.assertRaises(ValueError):
                MODULE.validate_preflight({**valid, **change}, "a" * 40, {"x": "b" * 64})

    def test_json_rejects_duplicate_members(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "input.json"
            path.write_text('{"endpoint":"one","endpoint":"two"}')
            with self.assertRaises(ValueError):
                MODULE.read_json(path)


if __name__ == "__main__":
    unittest.main()
