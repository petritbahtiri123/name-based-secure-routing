# ISP/Federation PoC Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and evidence a Docker-isolated ISP secure-route PoC with federation admission preflight while leaving existing NBSR protocol, authority, trust, cryptography, ACK, and loopback components unchanged.

**Architecture:** PoC-only TCP and UDP adapters bridge unchanged loopback listeners into three isolated Compose networks. The unchanged secure-route path invokes a fixed-target Origin Connector through the existing hashed stdin/stdout backend contract; a separate current-SHA federation admission preflight gates startup and is reported independently from the data plane.

**Tech Stack:** Python 3.14 orchestration/tests, Go connector/adapters, Rust release `nbsr-transport`, Docker Desktop/Compose, Linux bridge networks, JSON/Markdown/SHA-256 evidence.

**Spec:** `docs/superpowers/specs/2026-08-30-isp-federation-poc-design.md`

## Global Constraints

- Work only on `codex/nbsr-v3-wp0-wp1`; never modify, merge, rebase, or push `main`.
- Do not modify frozen authority, approved digests, Core v0.2, federation objects, RouteGrant, QUIC/TLS, ALPN, crypto, trust, authentication, authorization, replay, stream admission, ACK, or send completion.
- Keep the Go ACP, Go proxy, and Rust `wp8_interop_server` loopback behavior unchanged.
- Adapters are opaque PoC byte forwarders. They make no security, authority, origin-selection, retry, or fallback decision and import no NBSR authority/protocol packages.
- Publish no host ports; use no host networking, privileged containers, Docker socket mount, host firewall/route changes, or automatic installation.
- Never start, extend, import, or cite the root `LEGACY_REFERENCE_ONLY` Compose demo.
- The private origin is reachable only from the Origin Connector through `isp_b_private`; client and ISP-A must fail direct access by name and inspected IP.
- Preserve raw evidence without manual edits and derive summaries/checksums mechanically.
- Report independently: **A. secure-route network isolation**, **B. federation admission preflight**, and **C. live runtime federation = NOT CLAIMED**.
- Follow literal RED -> GREEN. Preserve bad-but-valid runs.
- Create one atomic federation/ISP-PoC commit after complete GREEN verification; no intermediate implementation commits.
- If UDP forwarding cannot preserve existing QUIC without a transport change, stop and classify INCONCLUSIVE.

## File map

| Path | Responsibility |
| --- | --- |
| `deploy/isp-federation-poc/compose.yaml` | Standalone topology and exact network membership. |
| `deploy/isp-federation-poc/Dockerfile` | Pinned release builders and non-root runtime targets. |
| `deploy/isp-federation-poc/adapter/` | Stdlib-only TCP/UDP byte adapters and tests. |
| `deploy/isp-federation-poc/private-origin/main.py` | Bounded private HTTP origin. |
| `client/nbsr-go-client/demo/cmd/nbsr-demo-origin-connector/` | Fixed-target backend-contract connector and tests. |
| `scripts/federation/isp_poc.py` | Closed types, readiness validation, derivation, checksums. |
| `scripts/federation/run_isp_federation_poc.py` | Build/run/scenario/evidence/cleanup CLI. |
| `tests/federation/test_isp_federation_poc.py` | Static, unit, orchestration, and live acceptance tests. |
| `docs/demo/isp-federation-poc.md` | Reproduction and non-claims. |
| `evidence/federation/isp-poc-{start_sha_12}/` | Raw and derived evidence; `{start_sha_12}` is the first 12 lowercase hex characters returned by `git rev-parse HEAD` before the run. |

---

### Task 1: PoC-only ISP-A TCP adapter

**Files:**
- Create: `deploy/isp-federation-poc/adapter/go.mod`
- Create: `deploy/isp-federation-poc/adapter/internal/forward/tcp.go`
- Create: `deploy/isp-federation-poc/adapter/internal/forward/tcp_test.go`
- Create: `deploy/isp-federation-poc/adapter/cmd/isp-a-tcp/main.go`
- Create: `deploy/isp-federation-poc/adapter/cmd/isp-a-tcp/main_test.go`

**Interfaces:**
- Consumes: `LISTEN_ADDR=0.0.0.0:18080`, `UPSTREAM_ADDR=127.0.0.1:{proxy_port}` where `{proxy_port}` is read from the validated Go readiness file, and `MAX_CONNECTIONS=16`.
- Produces: `ServeTCP(ctx context.Context, listener net.Listener, upstream string, maxConnections int, operationTimeout time.Duration) error`.

- [ ] **Step 1: Write RED tests** for real-socket byte identity, half-close, cancellation, capacity, unavailable upstream, literal loopback-only upstream, one target, and absence of NBSR/crypto/origin/fallback imports or keys.
- [ ] **Step 2: Run RED:** `go test ./cmd/isp-a-tcp ./internal/forward -run 'Test(TCP|Adapter)' -count=1` from the adapter module. Expect missing package/function failure.
- [ ] **Step 3: Implement minimum GREEN:** stdlib only; closed environment schema; fixed loopback upstream; at most 16 connections; two fixed buffers; close both directions on error; identifier-free logs; no retry.

Core shape:

```go
func ServeTCP(ctx context.Context, listener net.Listener, upstream string, limit int, timeout time.Duration) error {
    if !strings.HasPrefix(upstream, "127.0.0.1:") || limit != 16 { return errInvalidConfig }
    // Accept under a fixed semaphore; each accepted socket dials only upstream.
}
```

- [ ] **Step 4: Verify GREEN:** `go test ./cmd/isp-a-tcp ./internal/forward -count=1` and `go vet ./cmd/isp-a-tcp ./internal/forward`.

### Task 2: PoC-only ISP-B UDP adapter

**Files:**
- Create: `deploy/isp-federation-poc/adapter/internal/forward/udp.go`
- Create: `deploy/isp-federation-poc/adapter/internal/forward/udp_test.go`
- Create: `deploy/isp-federation-poc/adapter/cmd/isp-b-udp/main.go`
- Create: `deploy/isp-federation-poc/adapter/cmd/isp-b-udp/main_test.go`

**Interfaces:**
- Consumes: `LISTEN_ADDR=0.0.0.0:45980`, `UPSTREAM_ADDR=127.0.0.1:45979`, `MAX_PEERS=16`, `IDLE_TIMEOUT_SECONDS=20`.
- Produces: `ServeUDP(ctx context.Context, listener *net.UDPConn, upstream *net.UDPAddr, maxPeers int, idleTimeout time.Duration) error` with one connected upstream socket per exact peer.

- [ ] **Step 1: Write RED tests** for datagram identity, two-peer response isolation, capacity, idle cleanup, cancellation cleanup, unavailable upstream, no reroute, loopback-only upstream, and no NBSR/crypto/origin/fallback capability.
- [ ] **Step 2: Run RED:** `go test ./cmd/isp-b-udp ./internal/forward -run 'Test(UDP|Adapter)' -count=1`. Expect missing implementation failure.
- [ ] **Step 3: Implement minimum GREEN:** mutex-protected peer map; one loopback upstream socket per peer; bounded response copier; idle expiry; capacity rejection; close every socket on cancellation; never inspect datagrams.

Core state:

```go
type udpPeer struct {
    client *net.UDPAddr
    upstream *net.UDPConn
    lastSeen time.Time
}
type udpPeers struct { mu sync.Mutex; byClient map[string]*udpPeer }
```

- [ ] **Step 4: Verify GREEN:** `go test ./cmd/isp-b-udp ./internal/forward -count=1`, `go test -race ./internal/forward -count=1`, and `go vet ./cmd/isp-b-udp ./internal/forward`.

### Task 3: Fixed-target Origin Connector

**Files:**
- Create: `client/nbsr-go-client/demo/cmd/nbsr-demo-origin-connector/main.go`
- Create: `client/nbsr-go-client/demo/cmd/nbsr-demo-origin-connector/main_test.go`

**Interfaces:**
- Consumes: one request on stdin, compile-time target `private-origin:8080`, and `ISP_B_PRIVATE_CIDR`.
- Produces: one bounded response on stdout and `NBSR_ISP_POC_CONNECTOR_COMPLETE requests=0|1 status=ok|rejected|failed` on stderr, with one concrete value selected for each field.
- Test seam: `run(ctx context.Context, stdin io.Reader, stdout, stderr io.Writer, cidr string, resolver resolver, dialer dialer) error`.

- [ ] **Step 1: Write RED tests** for the exact valid request; wrong Host/name/port/method/path; NUL/trailing/oversize input; outside-CIDR or multiple DNS results; timeout; cancellation; oversized response; origin close; exactly one dial; zero fallback.
- [ ] **Step 2: Run RED:** `go test ./cmd/nbsr-demo-origin-connector -count=1` from `client/nbsr-go-client/demo`. Expect missing command failure.
- [ ] **Step 3: Implement minimum GREEN:** resolve once; require exactly one IPv4 address within the supplied private prefix; dial that IP only at port 8080; one deadline; bounded response; no redirect, proxy, retry, public target, or endpoint option.

Production target remains a constant:

```go
const originName = "private-origin"
const originPort = "8080"
func run(ctx context.Context, stdin io.Reader, stdout, stderr io.Writer, cidr string, r resolver, d dialer) error
```

- [ ] **Step 4: Verify GREEN:** `go test ./cmd/nbsr-demo-origin-connector -count=1` and `go vet ./cmd/nbsr-demo-origin-connector`.

### Task 4: Isolated Docker Compose topology

**Files:**
- Create: `deploy/isp-federation-poc/compose.yaml`
- Create: `deploy/isp-federation-poc/Dockerfile`
- Create: `deploy/isp-federation-poc/private-origin/main.py`
- Test: `tests/federation/test_isp_federation_poc.py`

**Interfaces:**
- Produces services `federation-preflight`, `private-origin`, `isp-b-runtime`, `isp-b-adapter`, `isp-a-runtime`, `isp-a-adapter`, `client-workload`.
- Produces exact networks `isp_a_access`, `federation_transit`, `isp_b_private`.

- [ ] **Step 1: Write RED static tests** parsing Compose and asserting exact memberships, `isp_b_private.internal: true`, no `ports`, host network, privilege, Docker socket, legacy extension/names, or root users. Require private origin only on `isp_b_private`, client only on `isp_a_access`, and ISP-A absent from `isp_b_private`.
- [ ] **Step 2: Run RED:** `python -m pytest tests/federation/test_isp_federation_poc.py -k 'compose or topology or legacy' -q`. Expect missing Compose failure.
- [ ] **Step 3: Implement minimum GREEN:** pinned digest bases, release builders, non-root runtime targets, project labels, read-only mounts, namespace-local adapters, no host ports. Private origin handles one bounded `GET /`, returns `hello from isolated private origin through NBSR`, and increments a file counter.

The network boundary must render as:

```yaml
networks:
  isp_a_access: {}
  federation_transit: {}
  isp_b_private:
    internal: true
```

- [ ] **Step 4: Verify GREEN:** rerun the focused pytest command and `docker compose -f deploy/isp-federation-poc/compose.yaml config --quiet`.

### Task 5: Federation preflight gate and endpoint-only readiness copy

**Files:**
- Create: `scripts/federation/__init__.py`
- Create: `scripts/federation/isp_poc.py`
- Modify: `tests/federation/test_isp_federation_poc.py`

**Interfaces:**
- Produces closed `PreflightResult` fields: schema, status, operator labels, federation-context hash, two attestation hashes, admitted-grant count, active-resource count.
- Produces `copy_transport_readiness(source: Path, destination: Path, endpoint: str) -> dict[str, object]`.
- Gate permits startup only for `status=PASS`, `admitted_grants=1`, `active_resources=0`.

- [ ] **Step 1: Write RED tests** requiring exact current-SHA valid/rejection federation test commands, closed preflight schema, failure-to-FAIL mapping, digest verification, and rejection when any readiness member other than endpoint changes.
- [ ] **Step 2: Run RED:** `python -m pytest tests/federation/test_isp_federation_poc.py -k 'preflight or readiness' -q`. Expect missing helpers.
- [ ] **Step 3: Implement minimum GREEN:** direct argv subprocesses, bounded JSON, unknown-member rejection, atomic UTF-8/LF writes, SHA-256 correlation, endpoint-only copy. Label this admission preflight, not live runtime federation.

Readiness validation compares a closed immutable field set:

```python
IMMUTABLE_READY = {"alpn", "ca_der", "client_cert_der", "client_key_der", "quic_version", "server_name", "tls_version"}
if any(original[key] != copied[key] for key in IMMUTABLE_READY):
    raise ValueError("transport readiness authority changed")
```

- [ ] **Step 4: Verify GREEN:** rerun focused tests plus `python -m pytest tests/federation/test_live_interoperability.py tests/federation/test_authorization.py -q`.

### Task 6: Bounded orchestrator and closed evidence schema

**Files:**
- Create: `scripts/federation/run_isp_federation_poc.py`
- Modify: `scripts/federation/isp_poc.py`
- Modify: `tests/federation/test_isp_federation_poc.py`

**Interfaces:**
- CLI: `python scripts/federation/run_isp_federation_poc.py --output {new_empty_directory} --project nbsr-isp-poc-{start_sha_8}`, with both brace tokens derived and validated as specified in Task 10.
- Scenario keys: scenario, claim_class, expected, actual, reason, protected_service_reachable, origin_request_delta, cleanup, status, commands, raw_files.
- Claim classes: `A_SECURE_ROUTE_NETWORK_ISOLATION`, `B_FEDERATION_ADMISSION_PREFLIGHT`, `C_LIVE_RUNTIME_FEDERATION_NOT_CLAIMED`.

- [ ] **Step 1: Write RED tests** for contained fresh output, validated project names, argv-only commands, failed-command rejection, raw-before-derived order, full checksums, closed scenario schema, and mandatory C status `NOT_CLAIMED`.
- [ ] **Step 2: Run RED:** `python -m pytest tests/federation/test_isp_federation_poc.py -k 'orchestrator or evidence or claim' -q`. Expect missing runner.
- [ ] **Step 3: Implement minimum GREEN:** ordered `validate -> build -> preflight -> topology -> scenarios -> cleanup -> derive`; raw stdout/stderr/exit recorded first; exact-project teardown in `finally`; zero-resource label inspection; no deletion outside output.

Closed claim labels:

```python
CLAIMS = (
    "A_SECURE_ROUTE_NETWORK_ISOLATION",
    "B_FEDERATION_ADMISSION_PREFLIGHT",
    "C_LIVE_RUNTIME_FEDERATION_NOT_CLAIMED",
)
```

- [ ] **Step 4: Verify GREEN:** rerun focused tests and `python -m ruff check scripts/federation tests/federation/test_isp_federation_poc.py`.

### Task 7: Authorized and unauthorized end-to-end routes

**Files:**
- Modify: `scripts/federation/run_isp_federation_poc.py`
- Modify: `tests/federation/test_isp_federation_poc.py`

**Interfaces:**
- Authorized result requires exact private-origin body and origin request delta 1.
- Wrong-route and unauthorized-preflight results require origin and connector deltas 0 and clean ownership counters.

- [ ] **Step 1: Write RED Docker tests** running each scenario in a fresh lifecycle. Client knows only `isp-a-adapter:18080` and `service-a.nbsr.test:8080`; wrong name/port fails before connector; wrong operator/trust preflight prevents data-plane startup.
- [ ] **Step 2: Run RED:** `python -m pytest tests/federation/test_isp_federation_poc.py -m docker -k 'authorized or unauthorized' -q`.
- [ ] **Step 3: Implement minimum GREEN:** use existing fixture generators; fixed Rust loopback UDP/45979; readiness copy to `isp-b-adapter:45980`; existing Go authority/client loopback; hashed connector backend map; workload enters only via ISP-A adapter.
- [ ] **Step 4: Verify GREEN:** rerun the Docker tests. Expect authorized PASS, fail-closed wrong route PASS, unauthorized preflight preventing startup, and zero fallback.

### Task 8: Direct-origin isolation

**Files:**
- Modify: `scripts/federation/run_isp_federation_poc.py`
- Modify: `tests/federation/test_isp_federation_poc.py`

**Interfaces:**
- Probe from both `client-workload` and `isp-a-runtime`, by DNS name and exact inspected private-origin IPv4.
- PASS requires four failed TCP attempts, origin request delta 0, origin membership only in `isp_b_private`, and no published ports.

- [ ] **Step 1: Write RED tests** requiring live inspect output plus name and inspected-IP probes; YAML-only or DNS-only proof is insufficient.
- [ ] **Step 2: Run RED:** `python -m pytest tests/federation/test_isp_federation_poc.py -m docker -k 'direct_origin or network_isolation' -q`.
- [ ] **Step 3: Implement minimum GREEN:** capture source container, target, timeout, exit code, output, origin counters, network IDs/subnets/memberships, and port inventory. Any successful direct connection is FAIL and preserved.
- [ ] **Step 4: Verify GREEN:** rerun focused Docker tests. Close the prior security INCONCLUSIVE only for this current-SHA Docker topology; never rewrite earlier raw evidence.

### Task 9: Adapter/session failure and restart-based recovery

**Files:**
- Modify: `scripts/federation/run_isp_federation_poc.py`
- Modify: `tests/federation/test_isp_federation_poc.py`

**Interfaces:**
- Failure cells stop ISP-A adapter, ISP-B adapter, and private origin before a new request.
- Recovery restarts the stopped component and opens a new route/session; live migration and automatic HA remain NOT CLAIMED.

- [ ] **Step 1: Write RED tests** asserting bounded failure, no alternate dial/direct reachability, connector/origin deltas, and zero connections/sessions/channels/streams/pending work after cooldown. Recovery must return the exact body once on a new lifecycle.
- [ ] **Step 2: Run RED:** `python -m pytest tests/federation/test_isp_federation_poc.py -m docker -k 'failure or recovery' -q`.
- [ ] **Step 3: Implement minimum GREEN:** exact service/project operations; unchanged timeouts; raw failure logs; existing cleanup gates; one-component restart; fresh one-shot state; no session-migration wording.
- [ ] **Step 4: Verify GREEN:** rerun focused Docker tests. Expect fail-closed failures, new-connection recovery, and zero leaked owned resources.

### Task 10: Cleanup, evidence, documentation, and atomic commit

**Files:**
- Create: `docs/demo/isp-federation-poc.md`
- Create: `evidence/federation/isp-poc-{start_sha_12}/` using the exact Task 10 derivation command.
- Modify: `.gitattributes` with an exact byte-stable rule for `evidence/federation/isp-poc-*/raw/**`.
- Modify: `scripts/verify_wp8_repository_safety.py` to add only `deploy/isp-federation-poc/adapter/go.mod` to the closed dependency inventory and to scan the new PoC source/evidence privacy scope.
- Modify: `tests/federation/test_repository_safety.py` with RED/GREEN inventory and privacy-scope assertions.
- Modify: `docs/superpowers/plans/2026-08-29-nbsr-evidence-closure.md` Task 7 status after evidence classification.

**Interfaces:**
- Final statuses: A and B each PASS/FAIL/INCONCLUSIVE; C exactly NOT CLAIMED.
- Cleanup: zero project containers/networks/volumes, connector children, NBSR connections/sessions/channels/streams/pending admissions/queues/locks.

- [ ] **Step 1: Run development evidence externally:** derive a collision-resistant development name and run outside the repository:

```powershell
$developmentId = [DateTime]::UtcNow.ToString('yyyyMMddHHmmss')
$developmentProject = 'nbsr-isp-poc-' + (git rev-parse --short=8 HEAD).Trim()
python scripts/federation/run_isp_federation_poc.py --output "C:\NBSR-build\isp-poc-development-$developmentId" --project $developmentProject
```

Diagnose before repository evidence and preserve bad runs externally.
- [ ] **Step 2: Run authoritative evidence:** derive exact names once, then run the campaign:

```powershell
$startSha = (git rev-parse HEAD).Trim()
$project = 'nbsr-isp-poc-' + $startSha.Substring(0,8)
$output = 'evidence/federation/isp-poc-' + $startSha.Substring(0,12)
python scripts/federation/run_isp_federation_poc.py --output $output --project $project
```

Raw files are write-once; derive analysis/summary/checksums; require zero cleanup inventory.
- [ ] **Step 3: Close dependency/privacy inventory RED -> GREEN:** first add assertions expecting the adapter `go.mod` and new PoC privacy roots, run `python -m pytest tests/federation/test_repository_safety.py -q` to observe the closed-inventory RED, update only the two explicit sets/scopes in `scripts/verify_wp8_repository_safety.py`, then rerun for GREEN.
- [ ] **Step 4: Run complete affected verification:** focused PoC tests; `tests/federation tests/security tests/demo`; Ruff; Go test/vet separately in client, demo, and adapter modules; Rust fmt, release Clippy `-D warnings`, release tests; dependency/privacy/safety checks; Compose config; `git diff --check`.
- [ ] **Step 5: Validate evidence and claims:** verify every checksum/source/image/executable hash, raw reference, network membership, scenario count, origin delta, and cleanup counter. Reject secrets, private keys, absolute user paths, unsupported claims, and any positive live-runtime-federation statement.
- [ ] **Step 6: Review complete diff:** confirm no frozen/protocol/runtime/loopback changes, legacy dependency, host port, fallback, or unrelated cleanup.
- [ ] **Step 7: Create one atomic commit:** explicitly stage only reviewed PoC paths, `.gitattributes`, safety inventory/test, Task 7 status, and evidence; run cached diff check; commit `test(federation): validate isolated isp secure route`; verify clean branch and unchanged main refs; stop before final packaging.

## Final acceptance matrix

| Claim | Required evidence | Status |
| --- | --- | --- |
| A. Secure-route network isolation | Authorized current secure-route response; origin only on `isp_b_private`; direct name/IP probes fail from client and ISP-A; no host ports/fallback; clean teardown | PASS / FAIL / INCONCLUSIVE |
| B. Federation admission preflight | Current-SHA valid preflight; unauthorized trust/operator prevents startup; digest correlation to unchanged destination artifacts | PASS / FAIL / INCONCLUSIVE |
| C. Live runtime federation | This plan introduces no distributed federation runtime | NOT CLAIMED |

Direct-origin evidence closes the previous security INCONCLUSIVE only when Claim A passes on the authoritative current-SHA topology. It does not modify earlier raw evidence or generalize beyond the recorded Docker host.
