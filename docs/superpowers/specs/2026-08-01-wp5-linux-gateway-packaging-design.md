# WP5 Linux gateway packaging and policy conformance design

**Status:** Approved for implementation on 2026-08-01 under delegated user
approval. The approved scope is deterministic Linux/OpenWrt packaging and
simulated policy-conformance evidence. It is not live platform validation or
production readiness.

## Goal

Define and implement the smallest fail-closed gateway package boundary that
can prove how an upgraded Linux/OpenWrt gateway would capture configured
Synthetic IP prefixes, preserve Name/Resolution and Secure Route/Tunnel plane
isolation, detect bypass, and roll back only NBSR-owned state.

## Approaches considered

1. **Windows WFP first.** This follows the existing Windows adapter, but a
   credible signed WFP component cannot be built or validated in this checkout.
2. **Live Linux/OpenWrt mutation.** This best matches the final operating
   model, but this Windows host cannot provide trustworthy live nftables,
   policy-routing, resolver, reboot, or clean-client evidence.
3. **Deterministic Linux/OpenWrt planner and conformance model.** This produces
   exact bounded installation intent, ownership state, verification results,
   and rollback operations without executing privileged commands. It is the
   approved approach because every behavior can be tested without claiming
   unavailable live evidence.

## Platform and interception decision

WP5 uses a Linux/OpenWrt-first profile. The planned interception mechanism is
nftables synthetic-destination matching combined with policy routing to a
local NBSR source-edge listener. A separate terminal reject rule covers the
configured Synthetic IP prefixes so capture ambiguity fails closed instead of
escaping to another route. Local DNS forwarding points clients at the NBSR
Name Node, while the Name/Resolution process remains separate from the Secure
Route/Tunnel process.

The implementation emits declarative operations only. It never invokes
`nft`, `ip`, `sysctl`, `uci`, a service manager, or a resolver command. A later
live-platform validation gate may translate these reviewed operations through
a privileged, signed or package-owned installer.

## Configuration boundary

`GatewayProfile` is immutable and contains:

- a unique package instance identifier;
- one operator-selected IPv4 Synthetic IP prefix;
- one operator-selected IPv6 ULA Synthetic IP prefix;
- a local Name Node address and port;
- a local source-edge listener address and TCP port;
- fixed nftables table/chain names owned by that instance;
- a policy-routing table in the lab range `10000..19999`; and
- a firewall mark in the lab range `0x4e420000..0x4e42ffff`.

There is no universal production prefix. IPv4 loopback, RFC 1918, and
`100.64.0.0/10` are rejected by this routed-gateway profile. IPv6 must be ULA.
Configuration is rejected if either prefix overlaps any supplied interface,
route, VPN, container, or reserved-prefix inventory entry. Exact matches are
also collisions unless the matching entry is proven to be owned by the same
package instance.

## Planner and ownership model

The planner consumes a validated profile plus a complete injected platform
snapshot and produces an ordered `GatewayPlan`:

1. install isolated nftables table and chains;
2. mark and redirect only the configured Synthetic IP destinations;
3. install policy rules and local routes for both address families;
4. install terminal synthetic-prefix reject rules;
5. configure local DNS forwarding to the Name Node; and
6. register independent health checks for the two planes.

Every operation has a stable identifier, resource kind, normalized arguments,
and inverse operation. No shell text is accepted as input and no operation may
address a resource outside the profile. The ownership journal records the
profile digest, pre-change resolver state, and only successfully applied NBSR
operation identifiers. Journal writes use the existing atomic private-file
boundary.

Rollback is generated in reverse application order. It may remove only
journaled NBSR resources and then restore the exact recorded resolver state.
Unreadable, mismatched, incomplete, or equivocated journal state fails closed
and produces no destructive rollback operations.

## Conformance and failure behavior

`GatewayVerifier` consumes the profile, plan, journal, and an injected
post-install snapshot. It returns a bounded structured report containing only
stable check codes and redacted resource identifiers. It checks:

- configured-prefix collision freedom;
- exact-prefix-only capture;
- a terminal reject path for both configured prefixes;
- matching policy rules, local routes, and firewall marks;
- Name Node forwarding and legacy resolver parity evidence;
- independent Name/Resolution and Secure Route/Tunnel health;
- ownership-journal agreement;
- absence of a direct-origin fallback operation;
- per-service policy attribution and bounded fair-share configuration; and
- rollback completeness without unrelated-resource mutation.

Missing, stale, ambiguous, or contradictory evidence is a failure. A failed
verification never recommends permissive fallback. Reports contain no Origin
Endpoint, raw client identifier, credential, key, token, or packet payload.

## Packaging artifacts

The repository package consists of:

- a Python configuration/planner module;
- a journal and rollback module;
- a conformance verifier module;
- an example lab profile with documentation-only prefixes;
- a dependency-free CLI that supports `plan`, `verify`, and `rollback-plan`
  over explicit JSON files; and
- focused tests plus protocol/status documentation.

The CLI writes JSON to standard output, performs no platform mutation, rejects
unknown fields, bounds input size and collection counts, and reports stable
errors without echoing sensitive input.

## Testing and evidence

All runtime behavior is implemented with focused RED-GREEN TDD. Tests cover
type and range validation, prefix collision and ownership exceptions, exact
operation order, shell-injection resistance, dual-stack fail-closed capture,
missing reject paths, resolver parity failure, plane failure containment,
journal corruption/equivocation, rollback ownership, report redaction,
deterministic CLI output, and unchanged frozen Core v0.1 files.

Fresh completion validation includes the focused WP5 suite, the full Python
suite, Ruff, dependency checks, Core vector regeneration, relevant Rust tests,
Rustfmt, Clippy with `-D warnings`, documentation checks, and `git diff
--check`. Independent review must cover platform-policy correctness, rollback
safety, privacy leakage, frozen-protocol scope, and documentation claims.

## Preserved boundaries and non-claims

WP5 does not allocate a message code, field key, state, wrapper, or other wire
value. It does not change frozen Core v0.1, select an OriginSet, connect or
forward to an Origin Endpoint, integrate NameRelay, enable cross-edge resume
or 0-RTT, implement WP6 replication, or claim production readiness.

It also does not claim a live nftables/TPROXY installation, OpenWrt package,
signed Windows component, clean no-agent client demonstration, legacy-site
parity on a real network, production Synthetic IP prefixes, or operational
rollback. Those require a separately approved and observed live-platform
exercise.
