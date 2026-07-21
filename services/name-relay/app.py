from __future__ import annotations

import argparse
import asyncio
import json
import os
import ssl
import subprocess
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
if (ROOT / "nbsr").is_dir():
    sys.path.insert(0, str(ROOT))


async def serve(host: str, port: int, certfile: Path, keyfile: Path) -> None:
    from nbsr.config import Settings
    from nbsr.name_relay import NameRelay
    from nbsr.name_security import validate_name_binding_public_key

    settings = Settings()
    validate_name_binding_public_key(settings)
    relay = NameRelay(settings=settings)
    tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    tls.minimum_version = ssl.TLSVersion.TLSv1_3
    tls.load_cert_chain(certfile, keyfile)
    server = await asyncio.start_server(relay.handle, host, port, ssl=tls)
    async with server:
        await server.serve_forever()


def assert_origin_hidden(client_visible_state: str) -> None:
    completed = subprocess.run(
        [
            "docker",
            "compose",
            "exec",
            "-T",
            "name-relay",
            "python",
            "-c",
            "import socket,sys; origin=socket.gethostbyname('facebook.test'); state=sys.stdin.read(); raise SystemExit(origin in state)",
        ],
        cwd=ROOT,
        input=client_visible_state,
        capture_output=True,
        check=False,
        text=True,
    )
    if completed.returncode != 0:
        raise RuntimeError("gateway-side assertion found the origin address in client-visible state")


def assert_origin_observed_relay() -> None:
    relay_id = subprocess.run(
        ["docker", "compose", "ps", "-q", "name-relay"],
        cwd=ROOT,
        capture_output=True,
        check=False,
        text=True,
    )
    if relay_id.returncode != 0 or not relay_id.stdout.strip():
        raise RuntimeError("could not identify the relay container")
    relay_networks = subprocess.run(
        [
            "docker",
            "inspect",
            "--format",
            "{{range .NetworkSettings.Networks}}{{println .IPAddress}}{{end}}",
            relay_id.stdout.strip(),
        ],
        cwd=ROOT,
        capture_output=True,
        check=False,
        text=True,
    )
    origin_logs = subprocess.run(
        ["docker", "compose", "logs", "--no-color", "name-origin"],
        cwd=ROOT,
        capture_output=True,
        check=False,
        text=True,
    )
    relay_addresses = {line.strip() for line in relay_networks.stdout.splitlines() if line.strip()}
    if relay_networks.returncode != 0 or origin_logs.returncode != 0 or not relay_addresses:
        raise RuntimeError("could not compare the origin peer with the relay network identity")
    if not any(f"ORIGIN_OBSERVED_PEER={address}" in origin_logs.stdout for address in relay_addresses):
        raise RuntimeError("the protected origin did not observe the relay container as its peer")


async def demo(
    control_url: str,
    control_ca: Path,
    relay_host: str,
    relay_port: int,
    relay_ca: Path,
    relay_server_name: str,
) -> None:
    from nbsr.dns_stub import ClientRoute, RouteTable
    from nbsr.name_security import ClientSession
    from nbsr.windows_agent import LoopbackInterceptor

    hostname = "facebook.test"
    session = ClientSession.generate()
    request = {
        "protocol_version": 1,
        "request_id": "name-route-demo",
        "hostname": hostname,
        "transport": "tcp",
        "client_nonce": "name-route-demo-nonce",
        "client_public_key": session.public_key_b64,
        "capabilities": ["tcp:443"],
    }
    control_tls = ssl.create_default_context(cafile=str(control_ca))
    async with httpx.AsyncClient(timeout=5.0, verify=control_tls) as client:
        response = await client.post(f"{control_url}/v1/name-routes/resolve", json=request)
        response.raise_for_status()
    route = response.json()
    client_route = ClientRoute(
        hostname=hostname,
        synthetic_ipv4=route["synthetic_ipv4"],
        synthetic_ipv6=route["synthetic_ipv6"],
        route_binding=route["route_binding"],
        expires_in=route["expires_in"],
    )
    route_table = RouteTable()
    route_table.put(client_route)
    interceptor = LoopbackInterceptor(
        route_table=route_table,
        client_session=session,
        relay_host=relay_host,
        relay_port=relay_port,
        gateway_id=route["gateway_id"],
        relay_tls_ca_path=relay_ca,
        relay_server_name=relay_server_name,
    )
    try:
        await interceptor.start(client_route, 80)
        await interceptor.start(client_route, 443)

        http_reader, http_writer = await asyncio.open_connection(route["synthetic_ipv4"], 80)
        http_writer.write(b"GET / HTTP/1.1\r\nHost: facebook.test\r\nConnection: close\r\n\r\n")
        await http_writer.drain()
        http_response = await http_reader.read()
        http_writer.close()
        await http_writer.wait_closed()

        origin_tls = ssl.create_default_context(cafile=str(relay_ca))
        https_reader, https_writer = await asyncio.open_connection(
            route["synthetic_ipv4"],
            443,
            ssl=origin_tls,
            server_hostname=hostname,
        )
        https_writer.write(b"GET / HTTP/1.1\r\nHost: facebook.test\r\nConnection: close\r\n\r\n")
        await https_writer.drain()
        https_response = await https_reader.read()
        https_writer.close()
        await https_writer.wait_closed()
    finally:
        await interceptor.close()

    client_visible_state = json.dumps(route, sort_keys=True)
    if b"hidden-origin-http" not in http_response or b"hidden-origin-https" not in https_response:
        raise RuntimeError("HTTP/HTTPS relay response did not match")
    assert_origin_hidden(client_visible_state)
    assert_origin_observed_relay()

    print(f"Requested name: {hostname}")
    print(f"Synthetic address: {route['synthetic_ipv4']}")
    print(f"NBSR gateway: tls://{relay_host}:{relay_port}")
    print("HTTP 80 response: hidden-origin-http")
    print("TLS 443 response: hidden-origin-https (facebook.test certificate and SNI verified)")
    print("PASS: no origin address appeared in client-visible state")
    print("PASS: protected origin observed the relay container peer")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="NBSR name relay and deterministic demo")
    subparsers = parser.add_subparsers(dest="command")
    serve_parser = subparsers.add_parser("serve")
    serve_parser.add_argument("--host", default=os.getenv("NBSR_NAME_RELAY_HOST", "0.0.0.0"))
    serve_parser.add_argument("--port", type=int, default=int(os.getenv("NBSR_NAME_RELAY_PORT", "8443")))
    serve_parser.add_argument("--certfile", type=Path, default=Path("/run/secrets/isp-relay-cert.pem"))
    serve_parser.add_argument("--keyfile", type=Path, default=Path("/run/secrets/isp-relay-key.pem"))
    demo_parser = subparsers.add_parser("demo")
    demo_parser.add_argument("--control-url", default="https://localhost:8444")
    demo_parser.add_argument("--control-ca", type=Path, default=ROOT / "secrets" / "isp-ca.pem")
    demo_parser.add_argument("--relay-host", default="127.0.0.1")
    demo_parser.add_argument("--relay-port", type=int, default=8443)
    demo_parser.add_argument("--relay-ca", type=Path, default=ROOT / "secrets" / "isp-ca.pem")
    demo_parser.add_argument("--relay-server-name", default="name-relay")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        if args.command in (None, "serve"):
            asyncio.run(
                serve(
                    getattr(args, "host", "0.0.0.0"),
                    getattr(args, "port", 8443),
                    getattr(args, "certfile", Path("/run/secrets/isp-relay-cert.pem")),
                    getattr(args, "keyfile", Path("/run/secrets/isp-relay-key.pem")),
                )
            )
        else:
            asyncio.run(
                demo(
                    args.control_url,
                    args.control_ca,
                    args.relay_host,
                    args.relay_port,
                    args.relay_ca,
                    args.relay_server_name,
                )
            )
    except (OSError, ssl.SSLError, RuntimeError, httpx.HTTPError, KeyError, asyncio.IncompleteReadError) as exc:
        print(f"name-route {args.command or 'serve'} failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
