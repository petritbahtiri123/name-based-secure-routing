# NBSR Security Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close all validated High and Medium NBSR security findings, apply the
selected structural hardening, verify preserved ISP and enterprise behavior,
and produce a clean auditable source package without changing `main`.

**Architecture:** Harden three independently testable boundaries: authenticated
transport and trusted enterprise metadata, relay destination policy, and local
secret/bounded state. Deployment manifests and operator documentation consume
those boundaries without introducing subscriber identity or traffic
inspection.

**Tech Stack:** Python 3.12+, FastAPI, Pydantic, PyJWT/EdDSA, cryptography,
asyncio streams, Envoy, OPA/Rego, Docker Compose, Kubernetes/Kind, pytest, Ruff.

## Global Constraints

- Work only on `codex/nbsr-security-hardening`; leave `main` unchanged.
- Do not push or open a pull request.
- Preserve the public ISP profile without mandatory identity, billing, mTLS, or
  content inspection.
- Require server-authenticated TLS on every client-facing control and relay
  path.
- Reject non-global relay destinations unless an exact trusted-origin rule
  authorizes both hostname and address.
- Preserve opaque HTTP/HTTPS relay and the enterprise OPA demonstration.
- Use test-first red/green cycles for each behavior change.
- Do not claim full NBSR Protocol Vision v2 or production readiness.

---

### Task 1: Transport and Enterprise Metadata Boundary

**Files:**
- Modify: `nbsr/windows_agent.py`
- Modify: `nbsr/demo_client.py`
- Modify: `nbsr/ticket_verifier.py`
- Modify: `nbsr/config.py`
- Modify: `scripts/bootstrap.py`
- Modify: `scripts/demo.py`
- Modify: `gateway/envoy.yaml`
- Modify: `compose.yaml`
- Modify: `tests/test_windows_agent.py`
- Modify: `tests/test_verifier.py`
- Modify: `tests/test_services.py`
- Modify: `tests/test_demo.py`

**Interfaces:**
- Produce: `RelayGateway.tls_ca_path: Path` as a required validated field.
- Produce: strict trusted metadata extraction with one value per required
  `x-nbsr-*` header.
- Produce: server certificates for enterprise control and gateway endpoints.

- [ ] **Step 1: Write failing tests**

Add tests proving that a relay gateway without a CA is rejected, duplicate or
missing trusted verifier metadata is denied, Envoy strips attacker-supplied
NBSR headers before adding derived values, and all public demo URLs are HTTPS.

- [ ] **Step 2: Verify RED**

Run:

```text
python -m pytest tests/test_windows_agent.py tests/test_verifier.py tests/test_services.py tests/test_demo.py -q --basetemp=.pytest-red-transport
```

Expected: the new assertions fail because TLS is optional, metadata falls back,
and Compose/Envoy still expose plaintext or ambiguous headers.

- [ ] **Step 3: Implement the narrow boundary**

Require a readable CA in `RelayGateway`; always build an SSL context and always
set `server_hostname`. Generate enterprise service certificates in bootstrap,
serve control and gateway over TLS, and update clients/health checks. Strip all
incoming `x-nbsr-*` headers in Envoy, add derived method/path/service with
overwrite semantics, reject missing or repeated values in the verifier, and
bind Envoy admin to `127.0.0.1`.

- [ ] **Step 4: Verify GREEN and preserved behavior**

Run the focused command from Step 2 and the existing enterprise authorization
tests. A valid ticket must still reach the fixed backend while spoofed metadata,
plaintext transport, and direct admin access fail.

- [ ] **Step 5: Commit**

```text
git add nbsr scripts gateway compose.yaml tests
git commit -m "fix: enforce authenticated transport boundaries"
```

### Task 2: Relay Destination Policy and Capability Scope

**Files:**
- Create: `nbsr/destination_policy.py`
- Modify: `nbsr/name_relay.py`
- Modify: `nbsr/name_service.py`
- Modify: `nbsr/name_security.py`
- Modify: `nbsr/name_control.py`
- Modify: `nbsr/config.py`
- Modify: `compose.yaml`
- Modify: `tests/test_name_relay.py`
- Modify: `tests/test_name_service.py`
- Modify: `tests/test_name_security.py`
- Modify: `tests/test_name_route_e2e.py`

**Interfaces:**
- Produce: `DestinationPolicy.validate(hostname: str, address: str) -> str`.
- Produce: `capability_ports(capabilities: Sequence[str]) -> tuple[int, ...]`.
- Preserve: exact-host trusted private-origin rule for `facebook.test`.

- [ ] **Step 1: Write failing tests**

Add table-driven tests for loopback, private, link-local, multicast,
unspecified, reserved, non-global, IPv4-mapped IPv6, and DNS-rebinding answers.
Add a positive global-address case and an exact trusted `facebook.test` private
origin case. Add capability tests proving `http` signs only port 80, `https`
only 443, both signs both, and unsupported/empty input fails before allocation.

- [ ] **Step 2: Verify RED**

Run:

```text
python -m pytest tests/test_name_relay.py tests/test_name_service.py tests/test_name_security.py tests/test_name_route_e2e.py -q --basetemp=.pytest-red-relay
```

Expected: private/non-global answers are accepted and bindings always contain
both ports.

- [ ] **Step 3: Implement the narrow boundary**

Create an `ipaddress`-based policy that accepts global unicast by default and
parses exact hostname/CIDR trusted-origin rules. Apply it to every resolved
literal directly before `open_connection`. Normalize capabilities to exact
ports and pass those ports through binding issuance and verification.

- [ ] **Step 4: Verify GREEN and exploit closure**

Run the focused command from Step 2. Re-run the original local loopback PoC and
an alternate IPv4-mapped/private case; no connection attempt may occur. Confirm
the explicit `facebook.test` Compose origin and a public test literal remain
admissible.

- [ ] **Step 5: Commit**

```text
git add nbsr compose.yaml tests
git commit -m "fix: constrain relay destinations and capabilities"
```

### Task 3: Bounded Allocation, Replay, and Admission

**Files:**
- Modify: `nbsr/synthetic.py`
- Modify: `nbsr/name_relay.py`
- Modify: `nbsr/name_control.py`
- Modify: `nbsr/name_service.py`
- Modify: `nbsr/config.py`
- Modify: `tests/test_synthetic.py`
- Modify: `tests/test_name_relay.py`
- Modify: `tests/test_name_service.py`

**Interfaces:**
- Produce: cursor/free/expiry heap allocator with a hard capacity.
- Produce: heap-backed `ReplayCache(max_entries: int)`.
- Produce: per-client/global admission limiter before allocation.

- [ ] **Step 1: Write failing tests**

Instrument address iteration to prove allocation does not restart at the first
host, exercise expiry/reuse and hard exhaustion, and prove replay insertion
remains bounded without a full dictionary scan. Exercise global and
session-thumbprint admission limits and confirm rejected requests allocate no
mapping.

- [ ] **Step 2: Verify RED**

Run:

```text
python -m pytest tests/test_synthetic.py tests/test_name_relay.py tests/test_name_service.py -q --basetemp=.pytest-red-state
```

Expected: current allocation and replay implementations scan historical state
and admission has no pre-allocation limit.

- [ ] **Step 3: Implement bounded structures**

Use monotonic address indexes, a free-index heap, and an expiry heap with stale
entry checks. Add a hard capacity no larger than the smaller dual-stack pool.
Use a replay dictionary plus expiry heap and reject at configured capacity after
pruning expired heap entries. Add a lock-protected token-window admission
limiter keyed by session public-key thumbprint and a global bucket.

- [ ] **Step 4: Verify GREEN and preserved renewal**

Run the focused command from Step 2 plus the end-to-end route tests. Existing
hostname renewal must keep its address; expired addresses may be reused; limits
must fail with stable client errors.

- [ ] **Step 5: Commit**

```text
git add nbsr tests
git commit -m "fix: bound anonymous routing state"
```

### Task 4: Secure Local Artifacts and Builder Context

**Files:**
- Create: `nbsr/secure_files.py`
- Create: `.dockerignore`
- Modify: `scripts/bootstrap.py`
- Modify: `nbsr/windows_agent.py`
- Modify: `tests/test_name_route_e2e.py`
- Modify: `tests/test_windows_agent.py`
- Create: `tests/test_secure_files.py`

**Interfaces:**
- Produce: `secure_write_private(path: Path, data: bytes) -> None`.
- Produce: `secure_write_text(path: Path, text: str) -> None`.
- Preserve: public certificate/public-key readability.

- [ ] **Step 1: Write failing tests**

On POSIX, assert private parents are `0700`, files are `0600`, replacement is
atomic, and a failure leaves the old file intact. On Windows, inspect the DACL
and assert no broad Users/Everyone read access. Run Docker context inspection
against sentinel files under `secrets/` and `tokens/`.

- [ ] **Step 2: Verify RED**

Run:

```text
python -m pytest tests/test_secure_files.py tests/test_name_route_e2e.py tests/test_windows_agent.py -q --basetemp=.pytest-red-files
```

Expected: bootstrap inherits ambient permissions and no `.dockerignore` blocks
sentinels.

- [ ] **Step 3: Implement secure writes and exclusions**

Write same-directory temporary files, flush and fsync, enforce permissions or a
protected Windows DACL, verify the result, and atomically replace the target.
Route private keys, bearer tokens, and the adapter ownership journal through
the helper. Add minimal builder-context exclusions.

- [ ] **Step 4: Verify GREEN**

Run focused tests and `docker build --no-cache` context checks when Docker is
available. Confirm bootstrap still produces all expected public and private
artifacts.

- [ ] **Step 5: Commit**

```text
git add .dockerignore nbsr scripts tests
git commit -m "fix: protect local security artifacts"
```

### Task 5: Kubernetes Least Privilege and Deployment Checks

**Files:**
- Modify: `deploy/kind/cluster.yaml`
- Modify: `deploy/kind/nbsr.yaml`
- Create: `scripts/verify-kind-security.ps1`
- Create: `scripts/verify-kind-security.sh`
- Modify: `tests/test_services.py`
- Modify: `docs/security-model.md`
- Modify: `docs/threat-model.md`

**Interfaces:**
- Produce: workload-specific ingress/egress NetworkPolicies.
- Produce: a Kind preflight that checks version, CNI enforcement, pod health,
  allowed flows, and denied flows.

- [ ] **Step 1: Write failing manifest tests**

Parse the manifest and prove there is no all-pod/all-namespace egress rule,
every selected workload has a policy, the Kind image is pinned, and scripts
contain executable positive/negative probes rather than source-text checks.

- [ ] **Step 2: Verify RED**

Run:

```text
python -m pytest tests/test_services.py -q --basetemp=.pytest-red-kind
```

Expected: the existing shared egress policy and unverified Kind configuration
fail the assertions.

- [ ] **Step 3: Implement least-privilege manifests and probes**

Split policies by component and labels, restrict namespaces and ports, pin the
Kind node image, and add scripts that fail if enforcement is unavailable or a
denied probe succeeds.

- [ ] **Step 4: Verify GREEN**

Run the focused manifest tests, `kubectl apply --dry-run=client`, and, when Kind
is installed, create the cluster, wait for all eight workloads with zero
restarts, and run both flow probes.

- [ ] **Step 5: Commit**

```text
git add deploy scripts tests docs
git commit -m "fix: enforce workload-specific network policy"
```

### Task 6: Documentation, Complete Validation, and Package

**Files:**
- Modify: `README.md`
- Modify: `docs/security-model.md`
- Modify: `docs/threat-model.md`
- Create: `docs/security-hardening-report.md`
- Create: `docs/vision-v2-conformance.md`
- Create: `artifacts/` only for the final external ZIP and checksum, not Git.

**Interfaces:**
- Produce: finding-by-finding disposition and exact residual-risk statement.
- Produce: clean source ZIP and matching SHA-256 file.

- [ ] **Step 1: Update reader documentation**

Document HTTPS trust bootstrap, destination policy, capacity controls, secure
file permissions, network-policy enforcement, operational limitations, and a
Vision v2 implemented/partial/not-implemented matrix. Record the unsealed Deep
Scan orchestration limitation without weakening the remediation evidence.

- [ ] **Step 2: Run complete verification**

Run focused security tests, full pytest with a writable base temp, Ruff, OPA
tests, Compose config, Docker builds and live attack/positive paths, and Kind
validation where available. Record exact pass/fail/unavailable results.

- [ ] **Step 3: Review the final diff**

Check scope, generated files, secrets, absolute paths, placeholders, debug
artifacts, and behavior claims. Re-run any affected focused test after a review
fix.

- [ ] **Step 4: Commit documentation and evidence**

```text
git add README.md docs
git commit -m "docs: record security hardening evidence"
```

- [ ] **Step 5: Package the committed tree**

Archive the feature commit with Git, extract it to a clean directory, verify no
`.git`, secrets, tokens, caches, or runtime artifacts exist, run static/package
checks against the extracted tree, and write a SHA-256 sidecar.

