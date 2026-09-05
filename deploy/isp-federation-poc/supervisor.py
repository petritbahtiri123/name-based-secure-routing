"""PoC-only container supervisor; no Docker socket, protocol or authority changes."""

import argparse
import builtins
from dataclasses import replace
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import shutil
import signal
import socket
import subprocess
import sys
import time

REPO = Path("/src")
DEMO = REPO / "client/nbsr-go-client/demo"
RUNTIME_BASE = DEMO / "test-results/nbsr-demo/runtime"
BINARIES = Path("/opt/nbsr/bin")
ARTIFACTS = (
    "vectors/wp8-f75-route-open/federation-context.cbor",
    "vectors/wp8-local-admission/source.cose",
    "vectors/wp8-local-admission/destination.cose",
)
READY_FIELDS = {"alpn", "ca_der", "client_cert_der", "client_key_der", "endpoint", "quic_version", "server_name", "tls_version"}


def closed_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON member")
        result[key] = value
    return result


def read_json(path):
    with path.open("rb") as stream:
        raw = stream.read(65537)
    if len(raw) > 65536:
        raise ValueError("JSON exceeds bound")
    return json.loads(raw, object_pairs_hook=closed_pairs)


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_suffix(".tmp")
    with temporary.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, sort_keys=True, allow_nan=False)
        stream.write("\n")
    temporary.chmod(0o600)
    temporary.replace(path)


def hash_file(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1048576), b""):
            h.update(chunk)
    return h.hexdigest()


def loopback(endpoint):
    host, port = endpoint.rsplit(":", 1)
    if host != "127.0.0.1" or not port.isascii() or not port.isdecimal() or not 1 <= int(port) <= 65535:
        raise ValueError("invalid loopback endpoint")
    return endpoint


def transport_copy(original):
    if not isinstance(original, dict) or set(original) != READY_FIELDS:
        raise ValueError("unexpected transport readiness members")
    if any(not isinstance(value, str) or not value for value in original.values()):
        raise ValueError("invalid readiness value")
    if (original["alpn"], original["quic_version"], original["server_name"], original["tls_version"]) != (
        "nbsr-quic-1",
        "v1",
        "destination.edge",
        "1.3",
    ):
        raise ValueError("transport profile changed")
    loopback(original["endpoint"])
    copied = {**original, "endpoint": "isp-b-adapter:45980"}
    if any(copied[key] != original[key] for key in READY_FIELDS - {"endpoint"}):
        raise ValueError("readiness authority changed")
    return copied


def tcp_projection(original):
    if (
        set(original) != {"Schema", "Proxy", "SyntheticIP", "State"}
        or original["Schema"] != "nbsr-demo-client-ready-v1"
        or original["State"] != "ready"
        or original["SyntheticIP"] != "127.0.0.2"
    ):
        raise ValueError("invalid client readiness")
    return {"schema": "nbsr-isp-adapter-ready-v1", "transport": "tcp", "upstream": loopback(original["Proxy"])}


def validate_preflight(value, sha, hashes):
    expected = {
        "schema",
        "status",
        "source_sha",
        "operators",
        "admitted_grants",
        "active_allocations",
        "limit_buckets",
        "artifacts",
        "live_runtime_federation",
    }
    if (
        set(value) != expected
        or value["schema"] != "nbsr-isp-preflight-v1"
        or value["status"] != "PASS"
        or value["source_sha"] != sha
        or value["operators"] != ["isp-a", "isp-b"]
        or value["artifacts"] != hashes
        or value["live_runtime_federation"] != "NOT_CLAIMED"
    ):
        raise ValueError("preflight binding failed")
    if any(type(value[key]) is not int for key in ("admitted_grants", "active_allocations", "limit_buckets")) or (
        value["admitted_grants"],
        value["active_allocations"],
        value["limit_buckets"],
    ) != (1, 0, 8):
        raise ValueError("preflight state not closed")


class Supervisor:
    def __init__(self):
        self.run_id = os.environ.get("NBSR_ISP_RUN_ID", "")
        self.sha = os.environ.get("NBSR_SOURCE_SHA", "")
        if not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?", self.run_id) or not re.fullmatch(r"[0-9a-f]{40}", self.sha):
            raise ValueError("explicit run identity required")
        if read_json(Path("/opt/nbsr/build-info.json"))["source_sha"] != self.sha:
            raise ValueError("image source mismatch")
        self.relative = f"test-results/nbsr-demo/runtime/{self.run_id}"
        self.root = RUNTIME_BASE / self.run_id
        self.build = Path("/opt/nbsr-build/nbsr-demo") / self.run_id
        self.children, self.streams = [], []
        self.stopping = False
        self.hashes = {name: hash_file(REPO / name) for name in ARTIFACTS}
        signal.signal(signal.SIGTERM, self.stop)
        signal.signal(signal.SIGINT, self.stop)

    def stop(self, *_):
        self.stopping = True

    def wait(self, path, seconds=45):
        deadline = time.monotonic() + seconds
        while not path.exists():
            if self.stopping or time.monotonic() > deadline or any(p.poll() is not None for p in self.children):
                raise RuntimeError("readiness wait failed")
            time.sleep(0.05)
        return path

    def launch(self, name, argv, cwd=DEMO, env=None):
        logs = self.root / "logs"
        logs.mkdir(exist_ok=True)
        out, err = (logs / f"{name}.stdout").open("x"), (logs / f"{name}.stderr").open("x")
        self.streams.extend((out, err))
        process = subprocess.Popen(argv, cwd=cwd, env=env, stdout=out, stderr=err)
        self.children.append(process)
        return process

    def gate(self):
        value = read_json(self.wait(self.root / "preflight.json"))
        validate_preflight(value, self.sha, self.hashes)

    def stage_binaries(self):
        self.build.mkdir(parents=True, exist_ok=False)
        hashes = {}
        for name in ("wp8_interop_server", "origin-connector"):
            target = self.build / name
            shutil.copyfile(BINARIES / name, target)
            target.chmod(0o500)
            hashes[name] = hash_file(target)
            if hashes[name] != hash_file(BINARIES / name):
                raise ValueError("artifact copy changed")
        return hashes

    def preflight(self):
        self.root.mkdir(exist_ok=False)
        for directory in ("client/bootstrap", "destination", "readiness", "logs", "evidence"):
            (self.root / directory).mkdir(parents=True, exist_ok=True, mode=0o700)
        command = [
            sys.executable,
            "-m",
            "pytest",
            "tests/federation/test_live_interoperability.py",
            "tests/federation/test_authorization.py",
            "-q",
        ]
        with (self.root / "logs/preflight.stdout").open("x") as out, (self.root / "logs/preflight.stderr").open("x") as err:
            result = subprocess.run(command, cwd=REPO, stdout=out, stderr=err, timeout=120)
        if result.returncode != 0:
            raise RuntimeError("federation tests failed")
        # Reuse the authentic test fixture APIs and record actual post-drain state.
        sys.path.insert(0, str(REPO))
        from tests.federation.test_live_interoperability import _wp7_lab, _admission
        from tests.federation.test_authorization import authenticated_context, context, evidence, DEST, SOURCE

        lab, route = _wp7_lab()
        admitted = _admission(lab, route).authorize(
            authenticated_context(context()),
            evidence(),
            replace(evidence(), operator_id=DEST, peer_operator_id=SOURCE, endpoint_operator_id=DEST),
            route,
            now_ms=150,
        )
        lab.drain(capability=admitted.receipt, started_ms=151, completed_ms=152)
        value = {
            "schema": "nbsr-isp-preflight-v1",
            "status": "PASS",
            "source_sha": self.sha,
            "operators": ["isp-a", "isp-b"],
            "admitted_grants": lab.admitted_grant_count,
            "active_allocations": lab.active_allocation_count,
            "limit_buckets": lab.limit_bucket_count,
            "artifacts": self.hashes,
            "live_runtime_federation": "NOT_CLAIMED",
        }
        validate_preflight(value, self.sha, self.hashes)
        write_json(self.root / "preflight.json", value)

    def isp_a(self):
        self.gate()
        hashes = self.stage_binaries()
        relative = self.relative
        self.launch(
            "authority",
            [
                str(BINARIES / "nbsr-demo-authority"),
                "--listen",
                "127.0.0.1:0",
                "--runtime",
                relative,
                "--client-bootstrap",
                relative + "/client/bootstrap",
                "--runtime-admission",
                relative + "/destination/runtime-admission.conf",
            ],
        )
        bootstrap = read_json(self.wait(self.root / "client/bootstrap/client-bootstrap.json"))
        if bootstrap.get("schema") != "nbsr-demo-client-bootstrap-v1" or not bootstrap.get("endpoint", "").startswith("https://"):
            raise ValueError("invalid authority readiness")
        loopback(bootstrap["endpoint"].removeprefix("https://"))
        destination = read_json(self.wait(self.root / "readiness/destination.json"))
        if destination["endpoint"] != "isp-b-adapter:45980":
            raise ValueError("transport copy missing")
        config = {
            "schema": "nbsr-demo-config-v1",
            "production_semantic": {
                "alpn": "nbsr-quic-1",
                "quic_version": "v1",
                "tls_version": "1.3",
                "stream_credit_profile": "nbsr-stream-credit-1",
            },
            "client": {
                "service_fixture": "testdata/service-a.json",
                "shared_synthetic_ip": "127.0.0.2",
                "proxy_endpoint": "127.0.0.1:0",
                "acp_endpoint": bootstrap["endpoint"],
                "destination_readiness": relative + "/readiness/destination.json",
                "application_transport": "tcp",
                "service_port": 8080,
            },
            "acp_fixture": {
                "classification": "DEMO FIXTURE — NOT PRODUCTION AUTHORITY",
                "public_fixture": relative + "/client/bootstrap/client-bootstrap.json",
            },
            "destination": {
                "authority_fixture": relative + "/destination/authority",
                "rust_artifact": {"path": str(self.build / "wp8_interop_server"), "sha256": hashes["wp8_interop_server"]},
            },
            "evidence": {"directory": relative + "/evidence"},
            "secrets": {"directory": relative + "/client/bootstrap"},
            "timeouts": {"handshake_seconds": 5, "operation_seconds": 15},
            "limits": {"max_proxy_connections": 16, "max_request_bytes": 4096},
        }
        write_json(self.root / "client/config.json", config)
        self.launch(
            "client",
            [
                str(BINARIES / "nbsr-demo-client"),
                "--config",
                relative + "/client/config.json",
                "--bootstrap",
                relative + "/client/bootstrap",
                "--ready",
                relative + "/readiness/client.json",
                "--runtime-root",
                relative,
                "--build-root",
                str(self.build),
            ],
        )
        client_ready = read_json(self.wait(self.root / "readiness/client.json"))
        write_json(Path("/projection-a/ready.json"), tcp_projection(client_ready))
        Path("/health/ready").touch(exist_ok=False)
        self.serve()

    def isp_b(self):
        self.gate()
        hashes = self.stage_binaries()
        cidr = ipaddress.IPv4Network(os.environ["ISP_B_PRIVATE_CIDR"], strict=True)
        if not any(cidr.subnet_of(ipaddress.IPv4Network(parent)) for parent in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")):
            raise ValueError("invalid private subnet")
        write_json(self.build / "origin-config.json", {"schema": "nbsr-isp-origin-config-v1", "private_cidr": str(cidr)})
        admission = self.wait(self.root / "destination/runtime-admission.conf")
        sys.path.insert(0, str(REPO))
        from scripts.performance.authority import write_loopback_authority

        authority = self.root / "destination/authority"
        write_loopback_authority(authority)
        backend = self.root / "destination/backend.map"
        backend.write_text(
            "NBSR-DEMO-BACKEND-MAP-v1\nservice_id=nbsr-demo-service-a-v1\nexecutable="
            + str(self.build / "origin-connector")
            + "\nsha256="
            + hashes["origin-connector"]
            + "\n"
        )
        original = self.root / "readiness/destination-original.json"
        gate, ack = self.root / "destination/start.gate", self.root / "destination/completion.ack"
        env = {key: value for key, value in os.environ.items() if not key.startswith("NBSR_")}
        env["NBSR_TASK10B_CAPTURE_PORT"] = "45979"
        destination = self.launch(
            "destination",
            [
                str(self.build / "wp8_interop_server"),
                "--ready",
                str(original),
                "--result",
                str(self.root / "destination/result.json"),
                "--authority-dir",
                str(authority),
                "--completion-ack",
                str(ack),
                "--demo-backend-map",
                str(backend),
                "--runtime-admission",
                str(admission),
                "--demo-start-gate",
                str(gate),
            ],
            cwd=REPO,
            env=env,
        )
        readiness = read_json(self.wait(original))
        write_json(self.root / "readiness/destination.json", transport_copy(readiness))
        write_json(
            Path("/projection-b/ready.json"),
            {"schema": "nbsr-isp-adapter-ready-v1", "transport": "udp", "upstream": loopback(readiness["endpoint"])},
        )
        Path("/health/ready").touch(exist_ok=False)
        self.wait(Path("/control/start"), seconds=120)
        gate.touch(exist_ok=False)
        self.wait(Path("/control/complete"), seconds=30)
        ack.touch(exist_ok=False)
        if destination.wait(timeout=15) != 0:
            raise RuntimeError("destination completion failed")
        write_json(
            self.root / "destination/supervisor-result.json", {"status": "PASS_PROCESS_EXIT", "owned_runtime_counters": "NOT_MEASURED"}
        )
        while not self.stopping:
            time.sleep(0.1)

    def serve(self):
        while not self.stopping:
            if any(child.poll() is not None for child in self.children):
                raise RuntimeError("owned runtime exited")
            time.sleep(0.1)

    def close(self):
        for child in self.children:
            if child.poll() is None:
                child.terminate()
        for child in self.children:
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait(timeout=5)
        for stream in self.streams:
            stream.close()


def adapter(role):
    prefix = Path("/projection-a" if role == "a" else "/projection-b")
    deadline = time.monotonic() + 60
    while not (prefix / "ready.json").exists():
        if time.monotonic() > deadline:
            raise RuntimeError("adapter readiness timeout")
        time.sleep(0.1)
    name = "isp-a-adapter" if role == "a" else "isp-b-adapter"
    addresses = {item[4][0] for item in socket.getaddrinfo(name, None, socket.AF_INET, socket.SOCK_STREAM)}
    if len(addresses) != 1:
        raise ValueError("ambiguous interface")
    address = addresses.pop()
    if not ipaddress.IPv4Address(address).is_private:
        raise ValueError("nonprivate interface")
    binary = BINARIES / ("isp-a-tcp" if role == "a" else "isp-b-udp")
    port = "18080" if role == "a" else "45980"
    os.execv(binary, [str(binary), "--listen", address + ":" + port, "--ready", str(prefix / "ready.json")])


def workload():
    request = b"CONNECT service-a.nbsr.test:8080 HTTP/1.1\r\nHost: service-a.nbsr.test:8080\r\n\r\n"
    # A separate control volume contains no authority, keys or origin address.
    Path("/control/start").touch(exist_ok=False)
    with socket.create_connection(("isp-a-adapter", 18080), timeout=15) as connection:
        connection.settimeout(15)
        connection.sendall(request)
        response = bytearray()
        while b"\r\n\r\n" not in response:
            chunk = connection.recv(1)
            if not chunk or len(response) >= 4096:
                raise ValueError("CONNECT failed")
            response.extend(chunk)
        if not response.startswith(b"HTTP/1.1 200 "):
            raise ValueError("CONNECT rejected")
        connection.sendall(b"GET / HTTP/1.1\r\nHost: service-a.nbsr.test:8080\r\nConnection: close\r\n\r\n")
        connection.shutdown(socket.SHUT_WR)
        response = bytearray()
        while True:
            chunk = connection.recv(4097 - len(response))
            if not chunk:
                break
            response.extend(chunk)
            if len(response) > 4096:
                raise ValueError("response exceeded bound")
        header, body = bytes(response).split(b"\r\n\r\n", 1)
        if not header.startswith(b"HTTP/1.1 200 ") or body != b"hello from isolated private origin through NBSR":
            raise ValueError("origin response mismatch")
    Path("/control/complete").touch(exist_ok=False)
    print("NBSR_ISP_POC_WORKLOAD status=PASS_BODY_ONLY", flush=True)


def failure_diagnostic(error):
    # Never format the exception, source text, frame locals or external paths.
    known_types = tuple(value for value in vars(builtins).values() if isinstance(value, type) and issubclass(value, Exception))
    known_types += (json.JSONDecodeError, subprocess.CalledProcessError, subprocess.TimeoutExpired)
    exception_type = type(error).__name__ if type(error) in known_types else "Exception"
    location = None
    trace = error.__traceback__
    while trace is not None:
        code = trace.tb_frame.f_code
        if code.co_filename == __file__:
            location = {"file": "supervisor.py", "function": code.co_name, "line": trace.tb_lineno}
        trace = trace.tb_next
    return {"status": "failed", "exception_type": exception_type, "location": location}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("role", choices=("preflight", "isp-a", "isp-b", "adapter-a", "adapter-b", "workload"))
    role = parser.parse_args().role
    if role.startswith("adapter-"):
        return adapter(role[-1])
    if role == "workload":
        return workload()
    supervisor = Supervisor()
    try:
        getattr(supervisor, role.replace("-", "_"))()
    finally:
        supervisor.close()


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print("NBSR_ISP_POC_SUPERVISOR status=failed diagnostic=" + json.dumps(failure_diagnostic(error)), flush=True)
        raise SystemExit(1) from None
