"""Bounded live two-relay fixture. No production wire or admission changes."""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import secrets
import socket
import ssl
import struct
import subprocess
import sys
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import jwt  # noqa: E402
from cryptography import x509  # noqa: E402
from cryptography.hazmat.primitives import serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import ec, ed25519  # noqa: E402
from cryptography.hazmat.primitives import hashes  # noqa: E402
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID  # noqa: E402

from nbsr.config import Settings  # noqa: E402
from nbsr.name_relay import NameRelay, RelayRejected, ResolvedEndpoint  # noqa: E402
from nbsr.name_security import ClientSession, issue_name_binding, sign_relay_proof  # noqa: E402
from nbsr.route_registry import RouteRegistry, RouteRegistryError  # noqa: E402

SCENARIOS = ("allowed", "policy_denied_b", "gateway_b_unavailable")
SUPERVISOR_SECONDS = 45


class TrialFailure(Exception):
    def __init__(self, details: dict):
        self.details = details
        super().__init__(json.dumps(details))


STAGES = {
    "gateway_a": {"admission_allowed", "policy_denied", "connect_started", "connected", "connect_failed"},
    "gateway_b": {"admission_allowed", "policy_denied", "connect_started", "connected", "connect_failed"},
    "service": {"request_received"},
    "client": {"request_started", "response_received", "rejection_received"},
}


class Trace:
    def __init__(self, component: str, observations: list[dict]):
        self.local_trace_id = uuid4().hex
        self.component = component
        self.events = observations
        self.sequence = 0

    def emit(self, stage: str) -> None:
        if stage not in STAGES.get(self.component, ()) or len(self.events) >= 24:
            raise ValueError("invalid diagnostic event")
        self.sequence += 1
        self.events.append({"local_trace_id": self.local_trace_id, "sequence": self.sequence,
                            "component": self.component, "stage": stage})


class LocalResolver:
    """Explicit fixture: logical port 443 maps to one owned loopback listener."""
    def __init__(self, hostname: str, port: int):
        self.hostname, self.port = hostname, port

    async def resolve(self, hostname: str, port: int) -> list[ResolvedEndpoint]:
        if hostname != self.hostname or port != 443:
            raise ValueError("unexpected fixture resolution")
        return [ResolvedEndpoint("127.0.0.1", self.port)]


class ObservedRegistry:
    def __init__(self, registry: RouteRegistry, trace: Trace):
        self.registry, self.trace = registry, trace

    def require_route(self, route_id):
        try:
            return self.registry.require_route(route_id)
        except RouteRegistryError:
            self.trace.emit("policy_denied")
            raise


class ObservedRelay(NameRelay):
    """Observe calls to the unchanged real relay, never replace its decisions."""
    def __init__(self, *, trace: Trace, expected: dict, **kwargs):
        super().__init__(**kwargs)
        self.trace, self.expected = trace, expected

    def _verify_admission(self, handshake):
        # One exact hop handshake per trial binds telemetry without a new wire field.
        # This check grants no authority; the original verifier still runs below.
        if handshake != self.expected:
            raise RelayRejected("unexpected diagnostic handshake")
        result = super()._verify_admission(handshake)
        self.trace.emit("admission_allowed")
        return result

    async def _connect_origin(self, *args, **kwargs):
        self.trace.emit("connect_started")
        try:
            result = await super()._connect_origin(*args, **kwargs)
        except RelayRejected:
            # This marks the failed connect phase, not a fabricated remote decision.
            self.trace.emit("connect_failed")
            raise
        self.trace.emit("connected")
        return result


def route_settings(component: str, hostname: str) -> Settings:
    key = ed25519.Ed25519PrivateKey.generate()
    pem = serialization.Encoding.PEM
    route = {"name": hostname, "route_id": component.replace("_", "-"),
             "origin_hostname": hostname, "ports": [443],
             "authorized_endpoints": ["127.0.0.1"], "allowed_cidrs": ["127.0.0.1/32"],
             "expected_http_host": hostname, "expected_tls_sni": hostname,
             "enabled": True, "policy_version": 1}
    # Explicit defaults prevent ambient NBSR_* settings from changing the trial.
    defaults = {name: field.default for name, field in Settings.model_fields.items()}
    defaults.update(name_binding_gateway_id=component, name_binding_ttl_seconds=60,
                    name_binding_private_key_pem=key.private_bytes(
                        pem, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()),
                    name_binding_public_key_pem=key.public_key().public_bytes(
                        pem, serialization.PublicFormat.SubjectPublicKeyInfo),
                    name_route_registry_json=json.dumps({"version": 1, "routes": [route]}))
    return Settings(**defaults)


def handshake(settings: Settings, hostname: str) -> dict:
    session = ClientSession.generate()
    binding = issue_name_binding(
        hostname=hostname, synthetic_ipv4="127.80.0.1", synthetic_ipv6="fd00:6e62:7372::1",
        gateway_id=settings.name_binding_gateway_id, session_public_key=session.public_key_b64,
        settings=settings, route_policy=RouteRegistry.from_settings(settings).require_name(hostname),
        ports=(443,),
    )
    # Decode only the locally issued ID to construct its proof; relay verifies it.
    route_id = jwt.decode(binding, options={"verify_signature": False})["jti"]
    nonce = uuid4().hex
    return {"hostname": hostname, "synthetic_address": "127.80.0.1", "port": 443,
            "gateway_id": settings.name_binding_gateway_id, "binding": binding,
            "route_id": route_id, "nonce": nonce,
            "proof": sign_relay_proof(session, route_id, nonce, 443)}


def frame(value: dict) -> bytes:
    encoded = json.dumps(value, separators=(",", ":")).encode()
    return struct.pack(">I", len(encoded)) + encoded


def tls_contexts(directory: Path, name: str) -> tuple[ssl.SSLContext, ssl.SSLContext, str]:
    key = ec.generate_private_key(ec.SECP256R1())
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, name)])
    now = datetime.now(UTC)
    cert = (x509.CertificateBuilder().subject_name(subject).issuer_name(subject)
            .public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(minutes=1)).not_valid_after(now + timedelta(hours=1))
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .add_extension(x509.SubjectAlternativeName([x509.DNSName(name)]), critical=False)
            .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
            .sign(key, hashes.SHA256()))
    cert_pem = cert.public_bytes(serialization.Encoding.PEM)
    password = secrets.token_bytes(32)
    key_path, cert_path = directory / (name + ".key"), directory / (name + ".crt")
    key_path.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                          serialization.BestAvailableEncryption(password)))
    cert_path.write_bytes(cert_pem)
    server = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server.load_cert_chain(cert_path, key_path, password=password)
    client = ssl.create_default_context(cadata=cert_pem.decode())
    for context in (server, client):
        context.minimum_version = context.maximum_version = ssl.TLSVersion.TLSv1_3
    # Only encrypted ephemeral keys touched disk; remove them after loading.
    key_path.unlink()
    cert_path.unlink()
    return server, client, cert_pem.decode()


async def gateway_worker(config: dict) -> dict:
    """Private stdin/stdout IPC; no trace ID or configuration is sent to a peer."""
    component = config["component"]
    events: list[dict] = []
    trace = Trace(component, events)
    settings = Settings(**config["settings"])
    registry_document = json.loads(settings.name_route_registry_json)
    if config["deny"]:
        registry_document["routes"][0]["enabled"] = False
    relay = ObservedRelay(trace=trace, expected=config["request"], settings=settings,
                          resolver=LocalResolver(config["target_name"], config["target_port"]),
                          route_registry=ObservedRegistry(RouteRegistry.from_json(json.dumps(registry_document)), trace))
    server = reservation = None
    tasks = set()
    errors = []
    trace_id_leaks = 0
    loop = asyncio.get_running_loop()
    initial_tasks = asyncio.all_tasks()
    loop.set_exception_handler(lambda _loop, _context: errors.append("callback_failed"))
    original_write = asyncio.StreamWriter.write

    def checked_write(writer, data):
        nonlocal trace_id_leaks
        if trace.local_trace_id.encode() in data:
            trace_id_leaks += 1
            raise ValueError("trace ID crossed local boundary")
        return original_write(writer, data)

    asyncio.StreamWriter.write = checked_write

    async def handle(reader, writer):
        task = asyncio.current_task()
        tasks.add(task)
        try:
            await relay.handle(reader, writer)
        except asyncio.CancelledError:
            raise
        except Exception:
            errors.append("handler_failed")
        finally:
            tasks.discard(task)

    try:
        with tempfile.TemporaryDirectory(prefix="nbsr-p1-gateway-") as temporary:
            tls, _, certificate = tls_contexts(Path(temporary), component.replace("_", "-") + ".test")
        if config["unavailable"]:
            reservation = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            reservation.bind(("127.0.0.1", 0))
            port = reservation.getsockname()[1]
        else:
            server = await asyncio.start_server(handle, "127.0.0.1", 0, ssl=tls,
                                                ssl_handshake_timeout=2, ssl_shutdown_timeout=1)
            port = server.sockets[0].getsockname()[1]
        print(json.dumps({"port": port, "certificate": certificate, "pid": os.getpid()}), flush=True)
        # Closing the parent's pipe also releases this wait after a parent crash.
        await asyncio.to_thread(sys.stdin.buffer.readline)
    finally:
        if server:
            server.close()
        if tasks:
            await asyncio.wait(tuple(tasks), timeout=1)
        await relay.close()
        if tasks:
            await asyncio.gather(*tuple(tasks), return_exceptions=True)
        if server:
            await server.wait_closed()
        if reservation:
            reservation.close()
        asyncio.StreamWriter.write = original_write
    pending = asyncio.all_tasks() - initial_tasks
    if pending:
        # Windows IOCP accept cancellation completes after Server.wait_closed().
        await asyncio.wait(pending, timeout=0.5)
    counts = {"listeners": len(server.sockets or ()) if server else 0,
              "tasks": len(asyncio.all_tasks() - initial_tasks), "connections": len(relay._connections)}
    if errors or tasks or any(counts.values()) or trace_id_leaks or (reservation and reservation.fileno() != -1):
        raise TrialFailure({"stage": "gateway_cleanup", "cleanup": counts,
                            "callback_errors": len(errors), "owned_tasks": len(tasks),
                            "trace_id_leaks": trace_id_leaks})
    return {"trace": events, "cleanup": counts, "trace_id_leaks": trace_id_leaks}


class GatewayProcess:
    def __init__(self, component: str):
        self.component = component
        self.process = None
        self.receipt = None

    async def start(self, settings, request, target_name, target_port, *, deny=False, unavailable=False):
        spawning = asyncio.create_task(asyncio.create_subprocess_exec(
            sys.executable, str(Path(__file__).resolve()), "--gateway",
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0))
        try:
            self.process = await asyncio.shield(spawning)
        except asyncio.CancelledError:
            self.process = await spawning
            raise
        config = {"component": self.component, "settings": settings.model_dump(mode="json"),
                  "request": request, "target_name": target_name, "target_port": target_port,
                  "deny": deny, "unavailable": unavailable}
        # Gateway needs only verification keys. Do not provision the issuer's private key.
        config["settings"]["name_binding_private_key_pem"] = None
        self.process.stdin.write(json.dumps(config).encode() + b"\n")
        await self.process.stdin.drain()
        ready = json.loads(await self.process.stdout.readline())
        if ready["pid"] != self.process.pid or ready["pid"] == os.getpid():
            raise ValueError("gateway process identity mismatch")
        client_tls = ssl.create_default_context(cadata=ready["certificate"])
        client_tls.minimum_version = client_tls.maximum_version = ssl.TLSVersion.TLSv1_3
        return ready["port"], client_tls

    async def close(self):
        if self.process is None:
            return
        try:
            output, errors = await asyncio.wait_for(self.process.communicate(b"stop\n"), timeout=3)
            if self.process.returncode != 0 or errors:
                raise TrialFailure({"stage": "gateway_exit", "component": self.component,
                                    "exit_code": self.process.returncode})
            self.receipt = json.loads(output)
            if any(self.receipt["cleanup"].values()) or self.receipt["trace_id_leaks"]:
                raise ValueError("gateway cleanup failed")
        finally:
            if self.process.returncode is None:
                self.process.kill()
                await asyncio.wait_for(self.process.wait(), timeout=1)


async def run_scenario(scenario: str) -> dict:
    if scenario not in SCENARIOS:
        raise ValueError("unknown scenario")
    observations: list[dict] = []
    traces = {component: Trace(component, observations) for component in ("client", "service")}
    servers, gateways, tasks, writers = [], [], set(), set()
    callback_errors = []
    loop = asyncio.get_running_loop()
    initial_tasks = asyncio.all_tasks()
    old_handler = loop.get_exception_handler()
    loop.set_exception_handler(lambda _loop, _context: callback_errors.append("callback_failed"))
    service_connections = service_requests = 0
    tls_verified = []
    response_verified = False
    client_writer = None
    # Private application challenge proves the response; it is not telemetry and
    # is never exported. Every component's diagnostic ID remains local.
    challenge = secrets.token_bytes(32)
    payload = b"P1 request " + challenge
    response = b"P1 response " + hashlib.sha256(challenge).digest()

    async def owned(handler, reader, writer):
        task = asyncio.current_task()
        tasks.add(task)
        writers.add(writer)
        try:
            await handler(reader, writer)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            callback_errors.append(type(exc).__name__)
        finally:
            await NameRelay._close_writer(writer)
            writers.discard(writer)
            tasks.discard(task)

    async def service(reader, writer):
        nonlocal service_connections, service_requests
        service_connections += 1
        if await reader.readexactly(len(payload)) != payload:
            raise ValueError("service correlation mismatch")
        service_requests += 1
        traces["service"].emit("request_received")
        writer.write(response)
        await writer.drain()
        await reader.read(1)

    async def listen(handler, context=None):
        options = {"ssl": context, "ssl_handshake_timeout": 2, "ssl_shutdown_timeout": 1} if context else {}
        server = await asyncio.start_server(
            lambda reader, writer: owned(handler, reader, writer), "127.0.0.1", 0, **options)
        servers.append(server)
        return server.sockets[0].getsockname()[1]

    async def cleanup():
        for server in servers:
            server.close()
        try:
            if client_writer is not None:
                try:
                    await asyncio.wait_for(NameRelay._close_writer(client_writer), timeout=1)
                except BaseException:
                    client_writer.transport.abort()
                    raise
                writers.discard(client_writer)
            if tasks:
                await asyncio.wait(tuple(tasks), timeout=2)
        finally:
            # A failed/cancelled TLS close must not skip owned process cleanup.
            exits = await asyncio.gather(*(gateway.close() for gateway in gateways), return_exceptions=True)
            for writer in tuple(writers):
                writer.transport.abort()
            for task in tuple(tasks):
                task.cancel()
            if tasks:
                await asyncio.gather(*tuple(tasks), return_exceptions=True)
            for server in servers:
                await server.wait_closed()
            failures = [result.details for result in exits if isinstance(result, TrialFailure)]
            if failures:
                raise TrialFailure({"stage": "gateway_cleanup", "failures": failures})
            if any(isinstance(result, BaseException) for result in exits):
                raise ValueError("gateway cleanup unconfirmed")

    try:
        async with asyncio.timeout(15):
            service_port = await listen(service)
            settings_b = route_settings("gateway_b", "private-service.test")
            request_b = handshake(settings_b, "private-service.test")
            gateway_b = GatewayProcess("gateway_b")
            gateways.append(gateway_b)
            port_b, client_b_tls = await gateway_b.start(
                settings_b, request_b, "private-service.test", service_port,
                deny=scenario == "policy_denied_b", unavailable=scenario == "gateway_b_unavailable")
            settings_a = route_settings("gateway_a", "gateway-b.test")
            request_a = handshake(settings_a, "gateway-b.test")
            gateway_a = GatewayProcess("gateway_a")
            gateways.append(gateway_a)
            port_a, client_a_tls = await gateway_a.start(settings_a, request_a, "gateway-b.test", port_b)
            if len({os.getpid(), gateway_a.process.pid, gateway_b.process.pid}) != 3:
                raise ValueError("gateway process isolation failed")
            reader, writer = await asyncio.open_connection(
                "127.0.0.1", port_a, ssl=client_a_tls, server_hostname="gateway-a.test",
                ssl_handshake_timeout=2, ssl_shutdown_timeout=1)
            client_writer = writer
            writers.add(writer)
            if writer.get_extra_info("ssl_object").version() != "TLSv1.3":
                raise ValueError("unexpected transport")
            tls_verified.append("gateway_a")
            traces["client"].emit("request_started")
            writer.write(frame(request_a))
            await writer.drain()
            admitted_a = await reader.readexactly(1)
            if admitted_a == b"\x01":
                # Real nested TLS to B through A's opaque byte forwarding.
                await writer.start_tls(client_b_tls, server_hostname="gateway-b.test",
                                       ssl_handshake_timeout=2)
                if writer.get_extra_info("ssl_object").version() != "TLSv1.3":
                    raise ValueError("unexpected transport")
                tls_verified.append("gateway_b")
                # Pipeline payload to prove B cannot leak it on policy rejection.
                writer.write(frame(request_b) + payload)
                await writer.drain()
                admitted_b = await reader.readexactly(1)
                if admitted_b == b"\x01":
                    if await reader.readexactly(len(response)) != response:
                        raise ValueError("response correlation mismatch")
                    response_verified = True
                    traces["client"].emit("response_received")
                elif admitted_b == b"\x00":
                    traces["client"].emit("rejection_received")
                else:
                    raise ValueError("invalid admission byte")
            elif admitted_a == b"\x00":
                traces["client"].emit("rejection_received")
            else:
                raise ValueError("invalid admission byte")
    finally:
        try:
            await asyncio.wait_for(cleanup(), timeout=8)
        finally:
            loop.set_exception_handler(old_handler)

    for gateway in gateways:
        if gateway.receipt is None:
            raise ValueError("missing gateway receipt")
        observations.extend(gateway.receipt["trace"])
    # Group by component: there is deliberately no fabricated global time order.
    observations.sort(key=lambda event: (event["component"], event["sequence"]))
    stages = [(event["component"], event["stage"]) for event in observations]
    expected_count = int(scenario == "allowed")
    terminal = {"allowed": ("client", "response_received"),
                "policy_denied_b": ("gateway_b", "policy_denied"),
                "gateway_b_unavailable": ("gateway_a", "connect_failed")}[scenario]
    cleanup_counts = {
        "listeners": sum(len(server.sockets or ()) for server in servers),
        "tasks": len(asyncio.all_tasks() - initial_tasks),
        "connections": len(writers),
        "processes": sum(gateway.process.returncode is None for gateway in gateways),
    }
    for gateway in gateways:
        for key, value in gateway.receipt["cleanup"].items():
            cleanup_counts[key] += value
    if (callback_errors or service_requests != expected_count or service_connections != expected_count
            or response_verified != bool(expected_count) or terminal not in stages
            or tasks or any(cleanup_counts.values()) or any(server.is_serving() for server in servers)):
        raise ValueError(f"trial verification failed: errors={callback_errors}, requests={service_requests}, "
                         f"connections={service_connections}, response={response_verified}, "
                         f"tasks={len(tasks)}, writers={len(writers)}, stages={stages}")
    return {"scenario": scenario, "status": "PASS", "correlation": "HARNESS_ONLY",
            "ordering": "PER_COMPONENT",
            "processes": {"gateways_started": len(gateways), "distinct": True,
                          "gateways_exited": sum(gateway.process.returncode == 0 for gateway in gateways)},
            "trace_id_leaks": sum(gateway.receipt["trace_id_leaks"] for gateway in gateways),
            "service_connections": service_connections, "service_requests": service_requests,
            "response_verified": response_verified, "tls": tls_verified,
            "cleanup": cleanup_counts, "trace": observations}


def terminal_color_enabled(mode: str) -> bool:
    return mode == "always" or (mode == "auto" and sys.stdout.isatty()
                               and "NO_COLOR" not in os.environ and os.environ.get("TERM") != "dumb")


def enable_windows_ansi():
    """Enable VT only on this interactive output handle; restore it on exit."""
    if os.name != "nt" or not sys.stdout.isatty():
        return lambda: None
    import ctypes
    from ctypes import wintypes

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetStdHandle.argtypes = [wintypes.DWORD]
    kernel.GetStdHandle.restype = wintypes.HANDLE
    kernel.GetConsoleMode.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    kernel.SetConsoleMode.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    handle = kernel.GetStdHandle(-11)
    mode = wintypes.DWORD()
    if kernel.GetConsoleMode(handle, ctypes.byref(mode)) and kernel.SetConsoleMode(handle, mode.value | 4):
        return lambda: kernel.SetConsoleMode(handle, mode.value)
    return lambda: None


def terminal_diagram(nodes, links, color):
    """Narrow boxed topology remains readable in an 80-column console."""
    rows = []
    for index, (label, code) in enumerate(nodes):
        border = "+" + "-" * 28 + "+"
        rows.extend(paint(line, code, color) for line in
                    (border, "|" + label.center(28) + "|", border))
        if index < len(links):
            blocked = links[index]
            code = 90 if blocked is None else (31 if blocked else 32)
            rows.append(paint("              " + ("X" if blocked else ":" if blocked is None else "|"),
                              code, color))
            rows.append(paint("              v", code, color))
    return "\n".join(rows)


def paint(text: str, code: int, color: bool) -> str:
    return f"\x1b[{code}m{text}\x1b[0m" if color else text


def terminal_failure(color: bool) -> str:
    return paint("[FAIL]", 31, color) + " Prova nuk perfundoi. Cleanup: I PAKONFIRMUAR."


def render_terminal_case(result: dict, *, color: bool) -> str:
    """Render only measured public fields; never print arbitrary diagnostics."""
    if result["status"] != "PASS" or any(result["cleanup"].values()):
        return terminal_failure(color)
    stages = {(event["component"], event["stage"]) for event in result["trace"]}
    titles = {"allowed": "LEJOHET", "policy_denied_b": "POLITIKA REFUZON NE B",
              "gateway_b_unavailable": "B NUK ESHTE I DISPONUESHEM"}
    def ok(label):
        return paint(label, 32, color)

    nodes = [("[Klienti]", 32), ("[A OK]", 32)]
    if ("gateway_b", "policy_denied") in stages:
        nodes += [("[B REFUZON]", 31), ("[Sherbimi: PA KERKESA]", 90)]
        links = [False, False, True]
        decision = "B zbatoi politiken. Payload-i nuk arriti te sherbimi."
        phase = "gateway_b.policy_denied"
    elif ("gateway_a", "connect_failed") in stages:
        nodes += [("[B NUK ARRIHET]", 31), ("[Sherbimi: PA KERKESA]", 90)]
        links = [False, True, None]
        decision = "Lidhja A -> B deshtoi. Nuk pretendohet vendim nga B."
        phase = "gateway_a.connect_failed"
    elif ("client", "response_received") in stages:
        nodes += [("[B OK]", 32), ("[Sherbimi OK]", 32)]
        links = [False, False, False]
        decision = "Sherbimi mori kerkesen; klienti verifikoi pergjigjen."
        phase = "service.request_received / client.response_received"
    else:
        return terminal_failure(color)
    diagram = terminal_diagram(nodes, links, color)
    process = result["processes"]
    counts = [result["service_connections"], result["service_requests"],
              process["gateways_exited"], process["gateways_started"]]
    if any(type(value) is not int or value < 0 for value in counts):
        return terminal_failure(color)
    index = SCENARIOS.index(result["scenario"]) + 1
    return "\n".join([
        "", paint(f"--- {index}/3  {titles[result['scenario']]} ---", 36, color),
        diagram, decision, "Faza e matur: " + phase,
        f"Sherbimi: lidhje={counts[0]} | kerkesa={counts[1]}.",
        f"Procese gateway: {counts[2]}/{counts[3]} perfunduan. Cleanup: 0 burime te mbetura.",
        ok("[PASS]") + " Sjellja e pritur u verifikua.",
    ])


async def run_all(on_result=None) -> dict:
    results = []
    for scenario in SCENARIOS:
        result = await run_scenario(scenario)
        results.append(result)
        if on_result is not None:
            on_result(result)
    return {"scope": "LIVE_LOOPBACK_PYTHON_RELAY_FIXTURE", "results": results}


async def supervised_run(on_result=None) -> dict:
    async with asyncio.timeout(SUPERVISOR_SECONDS):
        return await run_all() if on_result is None else await run_all(on_result)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--format", choices=("auto", "json", "terminal"), default="auto",
                        help="Default: terminal when interactive, raw JSON when redirected.")
    parser.add_argument("--color", choices=("auto", "always", "never"), default="auto",
                        help="Terminal colors; JSON is never colorized.")
    parser.add_argument("--gateway", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    terminal = not args.gateway and (args.format == "terminal" or
                                        (args.format == "auto" and sys.stdout.isatty()))
    color = terminal_color_enabled(args.color) if terminal else False
    restore_console = enable_windows_ansi() if color else lambda: None
    try:
        if terminal:
            print(paint("=== NBSR P1 | DY GATEWAY LOKALE ===", 36, color))
            print("2 procese gateway | TCP/TLS reale | trust/DNS fixture | jo prove multi-host")
            print("Jeshile = hap i kryer. Kuqe = bllokim/refuzim. Gri = nuk u arrit.")
            print("Refuzimi i pritur mund te jete i kuq; testi merr PASS kur sjellja eshte e sakte.", flush=True)
        if args.gateway:
            result = asyncio.run(gateway_worker(json.loads(sys.stdin.buffer.readline(65536))))
        elif terminal:
            result = asyncio.run(supervised_run(
                lambda item: print(render_terminal_case(item, color=color), flush=True)))
        else:
            result = asyncio.run(supervised_run())
        if terminal:
            print("\nID-te jane lokale; lidhja e vezhgimeve behet vetem nga testi.")
            print("Detajet e plota: --format json (nis nje prove te re).")
        else:
            print(json.dumps(result, indent=2))
        return 0
    except TrialFailure as failure:
        print(terminal_failure(color) if terminal else
              json.dumps({"status": "FAIL", "cleanup": "UNCONFIRMED", "details": failure.details}))
        return 1
    except (Exception, KeyboardInterrupt):
        # Never serialize raw exceptions, private paths or captured worker diagnostics.
        print(terminal_failure(color) if terminal else
              json.dumps({"status": "FAIL", "stage": "trial_or_cleanup", "cleanup": "UNCONFIRMED"}))
        return 1

    finally:
        restore_console()


if __name__ == "__main__":
    raise SystemExit(main())
