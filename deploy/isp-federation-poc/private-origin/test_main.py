"""Fixture tests; run after shared host measurement clearance."""

import importlib.util
from pathlib import Path
import tempfile
import unittest

SPEC = importlib.util.spec_from_file_location("isp_private_origin", Path(__file__).with_name("main.py"))
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class OriginTests(unittest.TestCase):
    def test_exact_response_and_valid_request(self):
        MODULE.validate_request(b"GET / HTTP/1.1\r\nHost: service-a.nbsr.test:8080\r\nConnection: close\r\n\r\n")
        headers, body = MODULE.RESPONSE.split(b"\r\n\r\n", 1)
        self.assertEqual(body, b"hello from isolated private origin through NBSR")
        self.assertIn(b"Content-Length: " + str(len(body)).encode(), headers)

    def test_rejects_body_malformed_wrong_target_and_oversize(self):
        valid = b"GET / HTTP/1.1\r\nHost: service-a.nbsr.test:8080\r\n\r\n"
        cases = [
            valid + b"x",
            valid.replace(b"GET", b"POST"),
            valid.replace(b" / ", b" /other "),
            valid.replace(b"service-a", b"service-b"),
            valid.replace(b":8080", b":80"),
            valid.replace(b"\r\n\r\n", b"\r\nContent-Length: 0\r\n\r\n"),
            valid.replace(b"\r\n\r\n", b"\r\nTransfer-Encoding: chunked\r\n\r\n"),
            valid.replace(b"\r\n\r\n", b"\r\nHost: service-a.nbsr.test:8080\r\n\r\n"),
            valid.replace(b"Host:", b" Host:"),
            valid + b"\x00",
            b"x" * 4097,
        ]
        for request in cases:
            with self.subTest(request=request[:30]), self.assertRaises(ValueError):
                MODULE.validate_request(request)

    def test_read_is_bounded_and_records_only_counts(self):
        class Socket:
            def __init__(self, chunks):
                self.chunks = iter(chunks)

            def settimeout(self, value):
                pass

            def recv(self, count):
                return next(self.chunks, b"")

        valid = b"GET / HTTP/1.1\r\nHost: service-a.nbsr.test:8080\r\n\r\n"
        self.assertEqual(MODULE.read_request(Socket([valid[:10], valid[10:]])), valid)
        with self.assertRaises(ValueError):
            MODULE.read_request(Socket([b"x" * 4097]))
        with tempfile.TemporaryDirectory() as temporary:
            counter = MODULE.Counter(Path(temporary))
            counter.record("connections")
            counter.record("accepted_requests")
            self.assertEqual(counter.values, {"connections": 1, "accepted_requests": 1, "rejected_requests": 0})
            self.assertNotIn("127.", (Path(temporary) / "counter.json").read_text())


if __name__ == "__main__":
    unittest.main()
