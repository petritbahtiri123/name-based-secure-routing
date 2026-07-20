from __future__ import annotations

import argparse
import asyncio
import json
import os
import struct
import subprocess
import sys
from pathlib import Path

import httpx
import jwt

ROOT = Path(__file__).resolve().parents[2]
if (ROOT / "nbsr").is_dir():
    sys.path.insert(0, str(ROOT))


async def serve(host: str, port: int) -> None:
    from nbsr.config import Settings
    from nbsr.name_relay import NameRelay

    relay = NameRelay(settings=Settings())
    server = await asyncio.start_server(relay.handle, host, port)
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


async def demo(control_url: str, relay_host: str, relay_port: int) -> None:
    from nbsr.name_security import ClientSession, sign_relay_proof

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
    async with httpx.AsyncClient(timeout=5.0) as client:
        response = await client.post(f"{control_url}/v1/name-routes/resolve", json=request)
        response.raise_for_status()
    route = response.json()
    claims = jwt.decode(route["route_binding"], options={"verify_signature": False, "verify_exp": False})
    nonce = "name-route-demo-relay-nonce"
    handshake = {
        "hostname": hostname,
        "synthetic_address": route["synthetic_ipv4"],
        "port": 443,
        "gateway_id": route["gateway_id"],
        "binding": route["route_binding"],
        "route_id": claims["jti"],
        "nonce": nonce,
        "proof": sign_relay_proof(session, claims["jti"], nonce, 443),
    }
    encoded_handshake = json.dumps(handshake, separators=(",", ":")).encode()
    reader, writer = await asyncio.open_connection(relay_host, relay_port)
    try:
        writer.write(struct.pack(">I", len(encoded_handshake)) + encoded_handshake + b"client-hello")
        await writer.drain()
        response_bytes = await reader.readexactly(len(b"hidden-origin:client-hello"))
    finally:
        writer.close()
        await writer.wait_closed()

    client_visible_state = json.dumps(route, sort_keys=True)
    if response_bytes != b"hidden-origin:client-hello":
        raise RuntimeError("opaque relay response did not match")
    assert_origin_hidden(client_visible_state)

    print(f"Requested name: {hostname}")
    print(f"Synthetic address: {route['synthetic_ipv4']}")
    print(f"NBSR gateway: {relay_host}:{relay_port}")
    print(f"Opaque response: {response_bytes.decode()}")
    print("PASS: no origin address appeared in client-visible state")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="NBSR name relay and deterministic demo")
    subparsers = parser.add_subparsers(dest="command")
    serve_parser = subparsers.add_parser("serve")
    serve_parser.add_argument("--host", default=os.getenv("NBSR_NAME_RELAY_HOST", "0.0.0.0"))
    serve_parser.add_argument("--port", type=int, default=int(os.getenv("NBSR_NAME_RELAY_PORT", "8443")))
    demo_parser = subparsers.add_parser("demo")
    demo_parser.add_argument("--control-url", default="http://localhost:8000")
    demo_parser.add_argument("--relay-host", default="127.0.0.1")
    demo_parser.add_argument("--relay-port", type=int, default=8443)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        if args.command in (None, "serve"):
            asyncio.run(serve(getattr(args, "host", "0.0.0.0"), getattr(args, "port", 8443)))
        else:
            asyncio.run(demo(args.control_url, args.relay_host, args.relay_port))
    except (OSError, RuntimeError, httpx.HTTPError, KeyError, jwt.PyJWTError, asyncio.IncompleteReadError) as exc:
        print(f"name-route {args.command or 'serve'} failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
