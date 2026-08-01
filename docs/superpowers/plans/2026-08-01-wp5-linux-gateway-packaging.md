# WP5 Linux Gateway Packaging Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a deterministic, fail-closed Linux/OpenWrt gateway packaging and policy-conformance model without privileged platform mutation or unsupported live-deployment claims.

**Architecture:** Immutable configuration and snapshot models feed a pure planner that emits normalized operations. A secure ownership journal permits exact reverse-order rollback planning, and a separate verifier compares intended and observed state using redacted stable check codes. A dependency-free CLI serializes these boundaries but never executes platform commands.

**Tech Stack:** Python 3.12-3.14, standard-library dataclasses/ipaddress/json/hashlib/argparse, existing `nbsr.secure_files`, pytest, Ruff.

## Global Constraints

- Work only on `codex/nbsr-v3-wp0-wp1`; do not touch `main`, merge, or push.
- Never access or stage `.codex-test-temp-w4/`.
- Do not execute `nft`, `ip`, `sysctl`, `uci`, resolver, or service-manager commands.
- Do not allocate wire values or change frozen Core v0.1 registries, schemas, states, wrappers, or vectors.
- Do not select an OriginSet, connect or forward to an Origin Endpoint, integrate NameRelay, enable 0-RTT or cross-edge resume, or implement WP6 behavior.
- Preserve exact-prefix capture, terminal reject, no direct fallback, independent planes, bounded input, redacted reports, and ownership-only rollback.
- Every runtime task starts with a focused failing test and ends with a focused passing test.
- Commit implementation separately from final evidence documentation.

---

### Task 1: Freeze the WP5 decision and documentation anti-drift boundary

**Files:**
- Create: `docs/protocol/wp5-linux-gateway-packaging-decision.md`
- Create: `tests/test_wp5_gateway_decision_documentation.py`
- Modify: `docs/superpowers/plans/2026-07-28-v3.6-protocol-roadmap.md`

**Interfaces:**
- Consumes: `docs/superpowers/specs/2026-08-01-wp5-linux-gateway-packaging-design.md`.
- Produces: exact textual gates required before runtime code exists.

- [ ] **Step 1: Write the failing documentation test** requiring Linux/OpenWrt-first scope, nftables plus policy-routing intent, terminal reject, pure planning, ownership-only rollback, exact non-claims, and live-platform validation remaining gated.
- [ ] **Step 2: Run `python -m pytest tests/test_wp5_gateway_decision_documentation.py -q`** and verify failure because the decision document is absent.
- [ ] **Step 3: Create the protocol decision** by freezing the approved design requirements and mark WP5 in the roadmap as approved/in progress at simulated conformance scope, not implemented or live validated.
- [ ] **Step 4: Run the focused documentation test and `tests/test_v36_documentation.py`** and verify pass.
- [ ] **Step 5: Commit only these documentation and test files** with `docs(wp5): freeze gateway packaging boundary`.

### Task 2: Validate profiles and collision inventories

**Files:**
- Create: `nbsr/gateway_profile.py`
- Create: `tests/test_gateway_profile.py`
- Modify: `nbsr/__init__.py`

**Interfaces:**
- Produces: `GatewayProfile.from_dict(value: object) -> GatewayProfile`, `PlatformSnapshot.from_dict(value: object) -> PlatformSnapshot`, `GatewayProfile.digest() -> str`, and `assert_collision_free(profile, snapshot) -> None`.
- `GatewayProfile` fields are `instance_id`, `synthetic_ipv4`, `synthetic_ipv6`, `name_node_host`, `name_node_port`, `source_edge_host`, `source_edge_port`, `policy_table`, and `firewall_mark`.
- `PlatformSnapshot` contains bounded immutable `NetworkResource` entries plus resolver and health evidence; JSON models reject unknown fields and collections above 256 entries.

- [ ] **Step 1: Write failing tests** for exact accepted lab values, unknown fields, non-canonical IDs/IPs/prefixes, forbidden IPv4 categories, non-ULA IPv6, ports, table/mark bounds, input collection bounds, and overlap rejection unless exact same-instance ownership is proven.
- [ ] **Step 2: Run `python -m pytest tests/test_gateway_profile.py -q`** and verify import failure because the models do not exist.
- [ ] **Step 3: Implement immutable strict models** using dataclasses and `ipaddress`; normalize JSON to canonical scalar/tuple types and compute the profile digest from sorted compact JSON.
- [ ] **Step 4: Implement collision checks** across interface, route, VPN, container, and reserved entries; allow only an exact prefix tagged with the same instance identifier.
- [ ] **Step 5: Run the focused tests and Ruff for the two files** and verify pass.
- [ ] **Step 6: Commit** with `feat(wp5): validate gateway profiles`.

### Task 3: Generate deterministic fail-closed gateway plans

**Files:**
- Create: `nbsr/gateway_plan.py`
- Create: `tests/test_gateway_plan.py`

**Interfaces:**
- Consumes: `GatewayProfile`, `PlatformSnapshot`, and `assert_collision_free`.
- Produces: `Operation(operation_id: str, kind: OperationKind, arguments: tuple[str, ...], inverse_kind: OperationKind, inverse_arguments: tuple[str, ...])`, `GatewayPlan(profile_digest: str, operations: tuple[Operation, ...])`, and `build_gateway_plan(profile, snapshot) -> GatewayPlan`.
- Operation kinds are a closed enum for nft table/chain/rule, policy rule/local route, terminal reject, DNS forwarding, and two independent plane health checks.

- [ ] **Step 1: Write failing tests** requiring stable dual-stack operation order, exact configured-prefix arguments, distinct plane health checks, terminal rejects after capture/local-route intent, deterministic identifiers, no origin/fallback operation, and rejection of newline/control/shell metacharacters in identifier-derived fields.
- [ ] **Step 2: Run `python -m pytest tests/test_gateway_plan.py -q`** and verify failure because the planner does not exist.
- [ ] **Step 3: Implement the closed operation model and planner** with stable SHA-256-derived operation identifiers and normalized argument vectors, never shell strings.
- [ ] **Step 4: Enforce fail-closed invariants** in `GatewayPlan.__post_init__`: unique identifiers, exact profile digest, both capture families, both reject families, matching marks/tables, no unknown operation kind, and no direct fallback.
- [ ] **Step 5: Run profile and planner tests plus Ruff** and verify pass.
- [ ] **Step 6: Commit** with `feat(wp5): plan fail closed gateway capture`.

### Task 4: Persist ownership and generate safe rollback plans

**Files:**
- Create: `nbsr/gateway_journal.py`
- Create: `tests/test_gateway_journal.py`

**Interfaces:**
- Consumes: `GatewayPlan`, its operation IDs, and `nbsr.secure_files.secure_write_text`.
- Produces: `OwnershipJournal.create(plan, resolver_before, applied_operation_ids)`, `OwnershipJournal.load(path)`, `OwnershipJournal.save(path)`, and `build_rollback_plan(plan, journal) -> GatewayPlan`.
- Journal schema is closed version `1`, contains `profile_digest`, bounded resolver state, ordered applied IDs, and a SHA-256 integrity digest over canonical fields.

- [ ] **Step 1: Write failing tests** for atomic round trip, mode-safe existing writer use, unknown/corrupt/equivocated data rejection, duplicate or unknown applied IDs, profile mismatch, partial application rollback, exact reverse order, resolver restoration last, and zero operations on invalid state.
- [ ] **Step 2: Run `python -m pytest tests/test_gateway_journal.py -q`** and verify failure because journal behavior is absent.
- [ ] **Step 3: Implement strict canonical journal serialization** with maximum 64 KiB file size, 256 applied IDs, stable integrity digest, and errors that do not echo file contents.
- [ ] **Step 4: Implement rollback planning** by selecting only journaled plan operations, reversing them, using their typed inverse vectors, and appending exact resolver restoration.
- [ ] **Step 5: Run journal/planner tests plus Ruff** and verify pass.
- [ ] **Step 6: Commit** with `feat(wp5): journal owned gateway state`.

### Task 5: Verify policy conformance with redacted evidence

**Files:**
- Create: `nbsr/gateway_verify.py`
- Create: `tests/test_gateway_verify.py`

**Interfaces:**
- Consumes: `GatewayProfile`, `GatewayPlan`, `OwnershipJournal`, and a post-install `PlatformSnapshot`.
- Produces: `CheckResult(code: CheckCode, passed: bool, resource_ref: str)`, `ConformanceReport(profile_ref: str, passed: bool, checks: tuple[CheckResult, ...])`, and `verify_gateway(profile, plan, journal, snapshot) -> ConformanceReport`.
- Check codes cover collision, capture v4/v6, reject v4/v6, policy route v4/v6, DNS forward, resolver parity, name-plane health, route-plane health, ownership, no-origin-fallback, service attribution, fair share, and rollback completeness.

- [ ] **Step 1: Write failing tests** for a complete passing snapshot and one focused failure for every check code; prove one plane can fail without erasing the sibling result, ambiguity fails, reports remain bounded/deterministic, and injected origin/credential/client strings never appear.
- [ ] **Step 2: Run `python -m pytest tests/test_gateway_verify.py -q`** and verify failure because the verifier does not exist.
- [ ] **Step 3: Implement stable redacted references** from kind and digest only, independent check evaluation, deterministic ordering, and aggregate failure on any missing or contradictory evidence.
- [ ] **Step 4: Add rollback-completeness verification** without executing operations and reject any snapshot claiming direct-origin fallback.
- [ ] **Step 5: Run all focused WP5 runtime tests plus Ruff** and verify pass.
- [ ] **Step 6: Commit** with `feat(wp5): verify gateway policy conformance`.

### Task 6: Add deterministic CLI and lab package artifacts

**Files:**
- Create: `nbsr/gateway_cli.py`
- Create: `config/wp5-linux-gateway-lab.json`
- Create: `tests/test_gateway_cli.py`
- Modify: `pyproject.toml`

**Interfaces:**
- Consumes: profile/snapshot/plan/journal/verifier JSON models.
- Produces: `nbsr-gateway-plan` console entry point with `plan`, `verify`, and `rollback-plan` subcommands; JSON output uses sorted compact encoding and stable error code `NBSR_GATEWAY_INPUT_REJECTED`.

- [ ] **Step 1: Write failing subprocess tests** for deterministic plan output, verify success/failure exit codes, rollback-plan output, 64 KiB input bounds, unknown fields, missing explicit paths, non-mutation, and non-echoing errors.
- [ ] **Step 2: Run `python -m pytest tests/test_gateway_cli.py -q`** and verify failure because the CLI is absent.
- [ ] **Step 3: Implement the argparse CLI** with explicit file arguments, bounded JSON reads, no subprocess/platform calls, compact sorted output, exit `0` for pass, `1` for conformance failure, and `2` for rejected input.
- [ ] **Step 4: Add the console script and example documentation-only profile** using `192.0.2.0/24` and `fd00:6e62:7372:5::/64`; the example is planning input only and not a production prefix recommendation.
- [ ] **Step 5: Run CLI and all focused WP5 tests plus Ruff** and verify pass.
- [ ] **Step 6: Commit** with `feat(wp5): package gateway conformance planner`.

### Task 7: Fresh validation, independent review, fixes, and evidence

**Files:**
- Modify: `docs/protocol/status.md`
- Modify: `docs/protocol/wp5-linux-gateway-packaging-decision.md`
- Modify: `docs/project-history.md`
- Modify: `SECURITY.md`
- Modify: `CONTRIBUTING.md`
- Modify: `docs/superpowers/plans/2026-07-28-v3.6-protocol-roadmap.md`
- Modify: this plan
- Create: `tests/test_wp5_runtime_documentation.py`

**Interfaces:**
- Consumes: all WP5 implementation and fresh validation evidence.
- Produces: reviewed completion record limited to deterministic planning and simulated policy conformance.

- [ ] **Step 1: Run focused WP5 tests**, then the full Python suite with an isolated writable `--basetemp` if needed.
- [ ] **Step 2: Run Ruff check/format, `pip check`, Core v0.1 and Core v0.2 regeneration, WP4 Python and Node vector verification, and `git diff --check`**.
- [ ] **Step 3: Run fresh Rust tests** with a non-OneDrive `CARGO_TARGET_DIR`, then Rustfmt and Clippy with `-D warnings`.
- [ ] **Step 4: Conduct independent security and documentation review** across the WP5 commit range for platform-policy correctness, rollback safety, input parsing, privacy, frozen protocol boundaries, and evidence claims.
- [ ] **Step 5: Fix every Critical or Important finding with a focused failing regression test first**, rerun affected validation, and repeat review until none remain.
- [ ] **Step 6: Write a failing runtime-documentation test** requiring exact fresh counts and every live-platform/production non-claim.
- [ ] **Step 7: Record only observed evidence** in status, decision, history, security, contribution guidance, roadmap, and this plan; run documentation tests and `git diff --check`.
- [ ] **Step 8: Commit evidence only** with `docs(wp5): record gateway conformance evidence`.
- [ ] **Step 9: Reconfirm branch, HEAD, `main`, clean staging/worktree, and remote divergence** without accessing `.codex-test-temp-w4/`; do not merge or push.

## Plan self-review

- **Spec coverage:** Tasks 2-6 cover configuration, collision safety, planning, ownership, rollback, conformance, CLI, and package input; Task 7 covers fresh evidence and review.
- **Scope:** No task executes privileged platform commands or claims live Linux/OpenWrt, no-agent, parity, operational rollback, production prefixes, origin forwarding, wire changes, or WP6 behavior.
- **Type consistency:** The immutable profile and snapshot feed the planner; the exact plan feeds journal and rollback; verifier consumes all three plus observed snapshot; CLI only serializes those interfaces.
- **No placeholders:** Every task names exact files, interfaces, focused failures, commands, and commit boundaries.
