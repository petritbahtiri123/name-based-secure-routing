"""Bounded private-origin fixture. Not an authorization or routing component."""

import argparse
import json
from pathlib import Path
import socket
import socketserver
import time

MAX_REQUEST = 4096
OPERATION_SECONDS = 2
BODY = b"hello from isolated private origin through NBSR"
RESPONSE = (
    b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nConnection: close\r\nContent-Length: "
    + str(len(BODY)).encode("ascii")
    + b"\r\n\r\n"
    + BODY
)


def validate_request(raw):
    if not raw or len(raw) > MAX_REQUEST or b"\x00" in raw or not raw.endswith(b"\r\n\r\n"):
        raise ValueError("invalid request")
    if raw.count(b"\r\n\r\n") != 1:
        raise ValueError("trailing request")
    lines = raw[:-4].split(b"\r\n")
    if lines[0] != b"GET / HTTP/1.1":
        raise ValueError("unsupported request")
    hosts = []
    for line in lines[1:]:
        if not line or line[:1] in (b" ", b"\t") or b":" not in line:
            raise ValueError("invalid header")
        name, value = line.split(b":", 1)
        if not name or any(byte not in b"!#$%&'*+-.^_`|~0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ" for byte in name):
            raise ValueError("invalid header name")
        if any(byte < 32 and byte != 9 or byte == 127 for byte in value):
            raise ValueError("invalid header value")
        name = name.lower()
        if name in (b"content-length", b"transfer-encoding"):
            raise ValueError("body framing forbidden")
        if name == b"host":
            hosts.append(value.strip())
    if hosts != [b"service-a.nbsr.test:8080"]:
        raise ValueError("wrong host")


def read_request(connection):
    deadline = time.monotonic() + OPERATION_SECONDS
    raw = bytearray()
    while b"\r\n\r\n" not in raw:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("request timeout")
        connection.settimeout(remaining)
        chunk = connection.recv(MAX_REQUEST + 1 - len(raw))
        if not chunk:
            raise ValueError("incomplete request")
        raw.extend(chunk)
        if len(raw) > MAX_REQUEST:
            raise ValueError("request too large")
    validate_request(bytes(raw))
    return bytes(raw)


class Counter:
    def __init__(self, directory):
        self.path = directory / "counter.json"
        # Each fixture lifecycle gets fresh writable state. Never overwrite evidence.
        if self.path.exists():
            raise ValueError("fresh counter directory required")
        self.values = {"connections": 0, "accepted_requests": 0, "rejected_requests": 0}
        self._write()

    def _write(self):
        temporary = self.path.with_suffix(".tmp")
        with temporary.open("x", encoding="utf-8") as stream:
            json.dump(self.values, stream, sort_keys=True)
            stream.write("\n")
        temporary.replace(self.path)

    def record(self, event):
        if event not in self.values:
            raise ValueError("unknown counter")
        self.values[event] += 1
        self._write()


class Handler(socketserver.BaseRequestHandler):
    def handle(self):
        self.server.counter.record("connections")
        try:
            read_request(self.request)
        except (ValueError, OSError, TimeoutError):
            self.server.counter.record("rejected_requests")
            return
        self.server.counter.record("accepted_requests")
        self.request.settimeout(OPERATION_SECONDS)
        try:
            self.request.sendall(RESPONSE)
            self.request.shutdown(socket.SHUT_WR)
        except OSError:
            return


class Server(socketserver.TCPServer):
    allow_reuse_address = False
    request_queue_size = 16

    def handle_error(self, request, client_address):
        # Never expose peer addresses, paths or payloads in fixture logs.
        print("NBSR_ISP_POC_ORIGIN status=failed", flush=True)
        raise SystemExit(1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-dir", type=Path, required=True)
    args = parser.parse_args()
    counter = Counter(args.state_dir)
    # Safe only in the origin's private-only namespace; Compose publishes no port.
    with Server(("0.0.0.0", 8080), Handler) as server:
        server.counter = counter
        print("NBSR_ISP_POC_ORIGIN status=ready", flush=True)
        server.serve_forever(poll_interval=0.2)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print("NBSR_ISP_POC_ORIGIN status=failed", flush=True)
        raise SystemExit(1) from None
