# NBSR Name Routing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and verify a Windows-first HTTP/HTTPS NBSR vertical slice that returns synthetic client-local addresses, signs anonymous proof-of-possession route bindings, privately resolves destinations at the gateway, and relays opaque traffic without exposing origin addresses to clients.

**Architecture:** A shared Python prototype core implements synthetic allocation, Ed25519 route bindings, private gateway resolution, and a TLS-capable TCP relay. A Windows-compatible local DNS stub and loopback interceptor exercise the same interfaces without requiring an unsigned WFP driver; the production WFP adapter remains a replaceable boundary.

**Tech Stack:** Python 3.12, FastAPI, Pydantic, PyJWT/EdDSA, cryptography, asyncio streams, dnslib, httpx, pytest, Docker Compose, Kubernetes manifests.

## Global Constraints

- Preserve the existing `payments.internal` JWT, OPA, Envoy, and ticket-verifier demonstration.
- The `isp` profile has no mandatory user identity, JWT, client certificate, billing integration, or content inspection.
- Real destination addresses must never appear in name-route API responses or client mapping state.
- Initial relay admission supports TCP ports 80 and 443 only.
- Route-binding admission lifetime defaults to 60 seconds; accepted connections may continue after admission expiry.
- Route binding keys remain separate from identity and enterprise route-ticket keys.
- The Windows prototype uses loopback synthetic addresses and does not claim to be a production WFP driver.
- Do not edit `dist/`, `node_modules/`, `ai/models/`, generated artifacts, or `package-lock.json`.

---

### Task 1: Synthetic Addressing and Hostname Model

**Files:**
- Create: `nbsr/name_model.py`
- Create: `nbsr/synthetic.py`
- Create: `tests/test_synthetic.py`

**Interfaces:**
- Produces: `normalize_hostname(value: str) -> str`
- Produces: `SyntheticMapping(hostname: str, ipv4: str, ipv6: str, expires_at: datetime)`
- Produces: `SyntheticAddressPool.allocate(hostname: str, now: datetime | None = None) -> SyntheticMapping`
- Produces: `SyntheticAddressPool.lookup(address: str, now: datetime | None = None) -> SyntheticMapping | None`

- [ ] **Step 1: Write failing normalization and allocation tests**

```python
def test_normalizes_dns_name():
    assert normalize_hostname("Facebook.COM.") == "facebook.com"

def test_reuses_live_mapping_and_never_contains_origin_address():
    pool = SyntheticAddressPool("127.80.0.0/29", "fd00:6e62:7372::/125", ttl_seconds=60)
    first = pool.allocate("facebook.test")
    second = pool.allocate("facebook.test")
    assert first == second
    assert first.ipv4.startswith("127.80.")
    assert "203.0.113.10" not in repr(first)

def test_pool_exhaustion_fails_closed():
    pool = SyntheticAddressPool("127.80.0.0/30", "fd00:6e62:7372::/126", ttl_seconds=60)
    pool.allocate("one.test")
    pool.allocate("two.test")
    with pytest.raises(SyntheticPoolExhausted):
        pool.allocate("three.test")
```

- [ ] **Step 2: Run the focused test and verify RED**

Run: `python -m pytest tests/test_synthetic.py -q`

Expected: collection fails because `nbsr.name_model` and `nbsr.synthetic` do not exist.

- [ ] **Step 3: Implement strict hostname normalization and a bounded dual-stack allocator**

```python
def normalize_hostname(value: str) -> str:
    hostname = value.rstrip(".").lower()
    if not hostname or len(hostname) > 253 or ".." in hostname:
        raise ValueError("Invalid NBSR hostname")
    labels = hostname.split(".")
    if any(not HOST_LABEL.fullmatch(label) for label in labels):
        raise ValueError("Invalid NBSR hostname")
    return hostname
```

The allocator must skip network/broadcast addresses where applicable, reuse an
unexpired hostname mapping, expire both forward and reverse indexes together,
and raise `SyntheticPoolExhausted` rather than returning a non-synthetic value.

- [ ] **Step 4: Run focused tests and verify GREEN**

Run: `python -m pytest tests/test_synthetic.py -q`

Expected: all synthetic-address tests pass.

- [ ] **Step 5: Commit the tested unit**

```bash
git add nbsr/name_model.py nbsr/synthetic.py tests/test_synthetic.py
git commit -m "feat: add synthetic name mappings"
```

### Task 2: Anonymous Ed25519 Route Bindings

**Files:**
- Create: `nbsr/name_security.py`
- Create: `tests/test_name_security.py`
- Modify: `nbsr/config.py`
- Modify: `scripts/bootstrap.py`

**Interfaces:**
- Consumes: `normalize_hostname(value: str) -> str`
- Produces: `ClientSession.generate() -> ClientSession`
- Produces: `issue_name_binding(...) -> str`
- Produces: `verify_name_binding(token: str, hostname: str, synthetic_address: str, port: int, gateway_id: str, settings: Settings) -> dict[str, Any]`
- Produces: `sign_relay_proof(session: ClientSession, route_id: str, nonce: str, port: int) -> str`
- Produces: `verify_relay_proof(claims: dict[str, Any], route_id: str, nonce: str, port: int, proof: str) -> None`

- [ ] **Step 1: Write failing binding and proof tests**

```python
def test_binding_round_trip_requires_client_proof(settings):
    session = ClientSession.generate()
    token = issue_name_binding(
        hostname="facebook.test",
        synthetic_ipv4="127.80.0.1",
        synthetic_ipv6="fd00:6e62:7372::1",
        gateway_id="edge-local",
        session_public_key=session.public_key_b64,
        settings=settings,
    )
    claims = verify_name_binding(token, "facebook.test", "127.80.0.1", 443, "edge-local", settings)
    nonce = "relay-nonce"
    proof = sign_relay_proof(session, claims["jti"], nonce, 443)
    verify_relay_proof(claims, claims["jti"], nonce, 443, proof)

@pytest.mark.parametrize("port", [22, 53, 853, 8443])
def test_binding_rejects_unapproved_port(settings, port):
    session = ClientSession.generate()
    token = issue_name_binding(
        hostname="facebook.test",
        synthetic_ipv4="127.80.0.1",
        synthetic_ipv6="fd00:6e62:7372::1",
        gateway_id="edge-local",
        session_public_key=session.public_key_b64,
        settings=settings,
    )
    with pytest.raises(SecurityError):
        verify_name_binding(token, "facebook.test", "127.80.0.1", port, "edge-local", settings)
```

Add explicit tests for tampering, expiry, wrong hostname, wrong synthetic
address, wrong gateway, wrong session key, and modified relay nonce.

- [ ] **Step 2: Run the focused test and verify RED**

Run: `python -m pytest tests/test_name_security.py -q`

Expected: collection fails because `nbsr.name_security` does not exist.

- [ ] **Step 3: Implement separate keys, binding claims, and proof-of-possession**

Add settings for `name_binding_private_key`, `name_binding_public_key`, issuer,
audience, gateway ID, and a 60-second bounded TTL. Bootstrap a separate
`name-binding-private.pem`/`name-binding-public.pem` pair. Store the raw Ed25519
session public key in a URL-safe encoding inside a confirmation claim and sign
the canonical message `route-id + newline + nonce + newline + port`.

- [ ] **Step 4: Run security tests and the existing security regression tests**

Run: `python -m pytest tests/test_name_security.py tests/test_security.py -q`

Expected: all tests pass; existing enterprise tickets remain unchanged.

- [ ] **Step 5: Commit the tested unit**

```bash
git add nbsr/name_security.py nbsr/config.py scripts/bootstrap.py tests/test_name_security.py
git commit -m "feat: sign anonymous name route bindings"
```

### Task 3: Name-Route API Without Address Disclosure

**Files:**
- Create: `nbsr/name_service.py`
- Create: `tests/test_name_service.py`
- Modify: `nbsr/control_plane.py`
- Modify: `tests/test_control_plane.py`

**Interfaces:**
- Consumes: `SyntheticAddressPool.allocate(...)`
- Consumes: `issue_name_binding(...)`
- Produces: `NameRouteService.resolve(hostname: str, session_public_key: str) -> NameRouteResponse`
- Produces: `POST /v1/name-routes/resolve`

- [ ] **Step 1: Write failing service and API tests**

```python
def test_name_route_response_contains_only_synthetic_addresses(service):
    response = service.resolve("facebook.test", ClientSession.generate().public_key_b64)
    encoded = response.model_dump_json()
    assert response.hostname == "facebook.test"
    assert response.synthetic_ipv4.startswith("127.80.")
    assert "203.0.113.10" not in encoded
    assert "resolved_addresses" not in encoded

def test_isp_route_does_not_require_authorization_header(client, settings):
    response = client.post("/v1/name-routes/resolve", json={
        "protocol_version": 1,
        "request_id": "request-1",
        "hostname": "facebook.test",
        "transport": "tcp",
        "client_nonce": "client-nonce",
        "client_public_key": ClientSession.generate().public_key_b64,
        "capabilities": ["http", "https"],
    })
    assert response.status_code == 200
    assert set(response.json()) == {
        "protocol_version", "request_id", "hostname", "synthetic_ipv4",
        "synthetic_ipv6", "gateway_id", "route_binding", "expires_in"
    }
```

- [ ] **Step 2: Run focused tests and verify RED**

Run: `python -m pytest tests/test_name_service.py tests/test_control_plane.py -q`

Expected: tests fail because the service and endpoint are missing.

- [ ] **Step 3: Implement the service and versioned API endpoint**

Validate protocol version `1`, transport `tcp`, nonempty capability values,
Ed25519 public-key encoding, request ID, nonce, and normalized hostname. Return
only the documented response fields. Keep the existing authenticated
`/v1/routes/resolve` endpoint unchanged.

- [ ] **Step 4: Run focused API tests and verify GREEN**

Run: `python -m pytest tests/test_name_service.py tests/test_control_plane.py -q`

Expected: all name-route and existing control-plane tests pass.

- [ ] **Step 5: Commit the tested unit**

```bash
git add nbsr/name_service.py nbsr/control_plane.py tests/test_name_service.py tests/test_control_plane.py
git commit -m "feat: resolve names to private NBSR routes"
```

### Task 4: Private Resolver and Opaque TCP Relay

**Files:**
- Create: `nbsr/name_relay.py`
- Create: `tests/test_name_relay.py`
- Modify: `nbsr/config.py`

**Interfaces:**
- Consumes: `verify_name_binding(...)`
- Consumes: `verify_relay_proof(...)`
- Produces: `PrivateResolver.resolve(hostname: str, port: int) -> list[ResolvedEndpoint]`
- Produces: `ReplayCache.consume(route_id: str, nonce: str) -> None`
- Produces: `NameRelay.handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None`

- [ ] **Step 1: Write failing resolver, admission, and relay tests**

```python
@pytest.mark.asyncio
async def test_relay_resolves_only_at_gateway_and_copies_opaque_bytes(settings):
    origin = await start_echo_origin(prefix=b"origin:")
    resolver = StaticResolver({"facebook.test": [("127.0.0.1", origin.port)]})
    relay = await start_name_relay(settings, resolver)
    response = await connect_with_valid_binding(relay, hostname="facebook.test", payload=b"opaque-tls-record")
    assert response == b"origin:opaque-tls-record"
    assert resolver.lookups == [("facebook.test", 443)]

@pytest.mark.asyncio
async def test_replay_nonce_is_rejected(settings):
    await connect_with_valid_binding(relay, nonce="same-nonce")
    with pytest.raises(RelayRejected):
        await connect_with_valid_binding(relay, nonce="same-nonce")
```

In the same test module, implement `start_echo_origin(prefix)`,
`StaticResolver(mapping)`, `start_name_relay(settings, resolver)`, and
`connect_with_valid_binding(relay, hostname="facebook.test",
payload=b"opaque", nonce=None)` as real loopback asyncio fixtures. The connect
helper must generate an ephemeral `ClientSession`, issue a real binding with the
test private key, sign a real relay proof, send the length-prefixed handshake,
and exchange bytes over actual sockets; it must not mock the relay.

Also prove that an expired token rejects new admission and that a connection
accepted before expiry continues relaying after the binding expires.

- [ ] **Step 2: Run focused relay tests and verify RED**

Run: `python -m pytest tests/test_name_relay.py -q`

Expected: collection fails because `nbsr.name_relay` does not exist.

- [ ] **Step 3: Implement bounded handshake, resolver, replay cache, and relay**

Read a four-byte big-endian handshake length followed by UTF-8 JSON. Reject
handshakes larger than 64 KiB, unknown fields, invalid bindings/proofs, repeated
nonces, and non-80/443 ports. Resolve with `getaddrinfo` inside the relay, try
bounded endpoints in order, then run two `asyncio` copy tasks until EOF. Never
serialize resolved endpoints back to the client.

- [ ] **Step 4: Run focused relay tests and verify GREEN**

Run: `python -m pytest tests/test_name_relay.py -q`

Expected: relay, expiry, replay, and active-connection tests pass.

- [ ] **Step 5: Commit the tested unit**

```bash
git add nbsr/name_relay.py nbsr/config.py tests/test_name_relay.py
git commit -m "feat: relay opaque named connections"
```

### Task 5: Windows-Compatible DNS Stub and Loopback Interceptor

**Files:**
- Create: `nbsr/dns_stub.py`
- Create: `nbsr/windows_agent.py`
- Create: `tests/test_dns_stub.py`
- Create: `tests/test_windows_agent.py`
- Modify: `pyproject.toml`

**Interfaces:**
- Consumes: `NameRouteService.resolve(...)` or the name-route HTTP endpoint
- Produces: `ClientRoute(hostname, synthetic_ipv4, synthetic_ipv6, route_binding, expires_in)`
- Produces: `BoundListener(host: str, port: int, server: asyncio.AbstractServer)`
- Produces: `DnsStub.resolve_query(packet: bytes) -> bytes`
- Produces: `RouteTable.put(mapping: ClientRoute) -> None`
- Produces: `LoopbackInterceptor.start(route: ClientRoute, local_port: int) -> BoundListener`

- [ ] **Step 1: Add `dnslib` and write failing A/AAAA and interception tests**

```python
def test_dns_stub_returns_synthetic_a_record_only(stub):
    answer = DNSRecord.parse(stub.resolve_query(DNSRecord.question("facebook.test", "A").pack()))
    assert str(answer.rr[0].rdata).startswith("127.80.")
    assert "203.0.113.10" not in str(answer)

@pytest.mark.asyncio
async def test_loopback_interceptor_uses_route_binding(agent, hidden_origin):
    route = await agent.resolve("facebook.test")
    response = await send_to_synthetic(route.synthetic_ipv4, agent.test_https_port, b"opaque")
    assert response == b"origin:opaque"
    assert agent.route_table.lookup(route.synthetic_ipv4).hostname == "facebook.test"
```

- [ ] **Step 2: Run focused client tests and verify RED**

Run: `python -m pytest tests/test_dns_stub.py tests/test_windows_agent.py -q`

Expected: collection fails because the DNS stub and Windows agent are missing.

- [ ] **Step 3: Implement DNS parsing and a replaceable interception boundary**

Support one-question IN/A and IN/AAAA requests, preserve the request ID, return
synthetic records with bounded TTL, and return standard DNS errors for malformed
or unsupported queries. The loopback interceptor binds only configured
synthetic addresses, looks up route state, creates a fresh proof nonce, opens
the NBSR relay, sends the bounded handshake, and copies bytes bidirectionally.
Keep Windows system-setting mutation behind a `WindowsNetworkAdapter` interface;
the first implementation records/restores owned state without installing a
kernel component.

- [ ] **Step 4: Run focused client tests and verify GREEN**

Run: `python -m pytest tests/test_dns_stub.py tests/test_windows_agent.py -q`

Expected: all DNS and loopback interception tests pass.

- [ ] **Step 5: Commit the tested unit**

```bash
git add pyproject.toml nbsr/dns_stub.py nbsr/windows_agent.py tests/test_dns_stub.py tests/test_windows_agent.py
git commit -m "feat: add Windows NBSR name stub"
```

### Task 6: Deployment, End-to-End Demo, and Full Validation

**Files:**
- Create: `services/name-relay/app.py`
- Create: `scripts/name-route-demo.ps1`
- Create: `scripts/name-route-demo.sh`
- Create: `tests/test_name_route_e2e.py`
- Modify: `compose.yaml`
- Modify: `deploy/kind/nbsr.yaml`
- Modify: `README.md`
- Modify: `docs/security-model.md`

**Interfaces:**
- Consumes: all previous public interfaces.
- Produces: a Compose/Kubernetes name-relay service and a deterministic Windows-first demo command.

- [ ] **Step 1: Write a failing end-to-end test**

```python
@pytest.mark.asyncio
async def test_name_route_end_to_end_hides_origin_address(stack):
    route = await stack.agent.resolve("facebook.test")
    response = await stack.agent.request(route, port=443, payload=b"client-hello")
    assert response == b"hidden-origin:client-hello"
    assert stack.origin.address not in route.model_dump_json()
    assert stack.origin.address not in stack.agent.export_client_state()
    assert stack.origin.observed_peer == stack.relay.address
```

Create the `stack` fixture as an `E2EStack` of real loopback services: a hidden
origin that records its peer address, a `StaticResolver`, a live `NameRelay`, a
live FastAPI name-route application, and a `WindowsAgent` using its loopback
adapter. `E2EStack.close()` must stop every listener in reverse creation order
so the test leaves no routes or ports behind.

- [ ] **Step 2: Run the end-to-end test and verify RED**

Run: `python -m pytest tests/test_name_route_e2e.py -q`

Expected: test fails because the assembled stack fixture and deployment entrypoint are missing.

- [ ] **Step 3: Add deployment wiring, deterministic demo, and precise documentation**

Add the relay as the only host-published name-routing data-plane service. Keep
the deterministic origin on an internal protected network and give it the
network alias `facebook.test`. Mount only the name-binding public key into the
relay. Document that the prototype loopback adapter proves the protocol but is
not a signed WFP driver, that HTTP/3 is excluded, and that the gateway operator
sees requested names and resolved destinations.

- [ ] **Step 4: Run focused, broad, lint, Compose, and manifest validation**

Run in order:

```powershell
python -m pytest tests/test_name_route_e2e.py -q
python -m pytest -q
python -m ruff check .
python -m ruff format --check .
docker compose config --quiet
docker compose build
docker compose up -d
./scripts/test.ps1
./scripts/name-route-demo.ps1
docker compose down
```

If `opa`, `kubectl`, and `kind` are installed, also run:

```powershell
opa test policy -v
kubectl apply --dry-run=client -f deploy/kind/nbsr.yaml
./scripts/kind-up.ps1
kubectl -n nbsr get all,networkpolicy
./scripts/kind-down.ps1
```

Expected: all available commands exit zero; the demo prints the requested name,
synthetic address, NBSR gateway, successful opaque response, and an assertion
that no origin address appeared in client-visible state.

- [ ] **Step 5: Audit requirements and commit the finished vertical slice**

Re-read `docs/superpowers/specs/2026-07-20-nbsr-name-routing-design.md`, map every
first-release requirement to a test or documented exclusion, run
`git diff --check`, inspect `git status --short`, and then commit only intended
source, test, deployment, script, and documentation files.

```bash
git add services/name-relay/app.py scripts/name-route-demo.ps1 scripts/name-route-demo.sh tests/test_name_route_e2e.py compose.yaml deploy/kind/nbsr.yaml README.md docs/security-model.md
git commit -m "feat: deliver NBSR name routing vertical slice"
```
