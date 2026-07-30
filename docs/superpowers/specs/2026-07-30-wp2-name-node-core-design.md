# WP2A Name Node Core Design

**Status:** Approved through explicit owner-delegated authorization

**Date:** 2026-07-30

**Scope:** Remaining WP2 Name Node core, signed local ServiceRecord registry,
resolution context, stable Synthetic IP mapping, DNS-compatible lab boundary,
and deterministic tests

**Non-scope:** public recursive DNS integration, native OriginSet publication,
WP3 transport, runtime relay integration, cloud deployment, production
synthetic prefixes, or changes to frozen Core v0.1

## Approval record

The protocol owner explicitly authorized Codex on 2026-07-30 to prepare this
plan, select the safest recommended approach, and approve it on the owner's
behalf. That delegated approval applies only to the wire-neutral WP2A design
below. It does not approve any new numeric key, message code, error code,
state, transition, critical extension, COSE wrapper, Core v0.2 object, public
DNS dependency, or WP3 behavior.

## Goal

Build the smallest independently testable Name Node core that:

- classifies configured names as signed NBSR service, constrained legacy
  service, or negative/error;
- returns a Synthetic IP for every successful resolution;
- never returns or logs an origin endpoint to the client;
- verifies signed ServiceRecord and Revocation objects using the frozen WP1
  API;
- creates and stores a bounded RouteIntent and non-exported Resolution Context;
- consumes the implemented `LegacyOriginCache` only through an injected
  discovery boundary;
- keeps Synthetic IP mappings stable while internal reachability changes; and
- remains available independently from WP3 transport.

WP2A is a lab-grade protocol boundary. It prepares secure route state but does
not establish a tunnel.

## Approaches considered

### A. Isolated Name Node core with injected upstreams — approved

Add focused registry, resolution-state, orchestration, and lab DNS modules.
Reuse the frozen `nbsr.protocol` API, `SyntheticAddressPool`,
`LegacyOriginCache`, and `DnsStub`. Inject time, random identifiers, legacy DNS
snapshots, and trust contexts so tests use no public network.

**Advantages:** smallest security surface, deterministic TDD, no Core v0.1
impact, no public resolver dependency, and clean future replacement of the lab
adapters.

**Cost:** real recursive DNS, DNSSEC validation library integration, Web PKI
origin validation, and production persistence remain separately gated.

### B. Full recursive resolver and UDP/TCP service immediately — deferred

Implement recursive DNS, DNSSEC, SVCB/HTTPS, Web PKI validation, persistence,
and listeners in one phase.

**Reason deferred:** the DNSSEC requirement level, Web PKI trust model,
production timeout values, and platform deployment profile remain pending.
Combining them would hide multiple security decisions inside one runtime task.

### C. Extend the historical route registry and relay service — rejected

Reuse `RoutePolicy` as the protocol service registry and connect the existing
relay directly.

**Reason rejected:** that prototype policy embeds origin hostnames and
authorized endpoint addresses. It does not represent the frozen signed
ServiceRecord, would mix service identity with reachability, and would make
the old demonstration architecture the new protocol boundary.

## Architecture

WP2A contains four isolated units:

1. `SignedServiceRegistry` validates and stores signed ServiceRecord and
   Revocation objects using caller-supplied Ed25519 trust contexts.
2. `ResolutionContextStore` owns bounded, expiring reverse state from Synthetic
   IP to a RouteIntent and internal reachability reference.
3. `NameNode` classifies a canonical name, obtains trusted service metadata,
   allocates or reuses a Synthetic IP, creates the RouteIntent, and commits the
   binding atomically.
4. `NameNodeDnsAdapter` converts successful Name Node results into the existing
   `DnsStub` client response shape. A separate loopback-only lab listener may
   expose UDP and TCP DNS after the core passes all focused tests.

```text
DNS question
  -> DnsStub / NameNodeDnsAdapter
  -> NameNode.resolve()
       -> SignedServiceRegistry OR configured LegacyServicePolicy
       -> injected LegacySnapshotProvider when legacy
       -> LegacyOriginCache (internal only)
       -> SyntheticAddressPool
       -> RouteIntent
       -> ResolutionContextStore
  -> Synthetic A/AAAA response only
```

OriginEndpoint values remain inside the legacy cache and resolution binding.
They never enter `ClientRoute`, DNS answers, client-visible exceptions, or
normal client telemetry.

## Stable internal interfaces

The implementation plan freezes these Python-only interfaces. They are not new
wire objects.

```python
class NameClassification(StrEnum):
    NBSR_SERVICE = "nbsr-service"
    LEGACY_SERVICE = "legacy-service"


@dataclass(frozen=True, slots=True)
class LegacyServicePolicy:
    canonical_name: str
    service_id: str
    service_record_generation: int
    source_operator_id: str
    source_edge_id: str
    destination_operator_id: str
    destination_edge_set: tuple[str, ...]
    allowed_ports: tuple[int, ...]
    policy_hash: bytes
    issuer_id: bytes
    origin_name: str
    allowed_networks: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class NameResolution:
    classification: NameClassification
    canonical_name: str
    synthetic_ipv4: str
    synthetic_ipv6: str
    route_id: bytes
    expires_at: int
```

`NameResolution` is the client-facing result and contains no OriginSet,
endpoint, origin name, key material, or reusable authorization credential.

```python
class SignedServiceRegistry:
    def install_record(
        self,
        cose_sign1: bytes,
        *,
        now: int,
    ) -> ServiceRecord: ...

    def apply_revocation(
        self,
        cose_sign1: bytes,
        *,
        now: int,
    ) -> Revocation: ...

    def resolve(
        self,
        canonical_name: str,
        *,
        now: int,
    ) -> ServiceRecord | None: ...
```

The registry constructor receives separate caller trust contexts for record
owners and revocation issuers. `install_record` verifies COSE, enforces
payload `kid`, validity and monotonically increasing sequence, and updates
state only after full validation. `apply_revocation` verifies issuer binding,
generation tombstones, target digest/sequence, and revocation mode. An invalid
configured NBSR record is a hard security failure, never a signal to try
legacy DNS.

```python
@dataclass(frozen=True, slots=True)
class ResolutionBinding:
    mapping: SyntheticMapping
    route_intent: RouteIntent
    classification: NameClassification
    originset: DerivedOriginSet | None
    resolution_context_id: bytes = field(repr=False)
    expires_at: int


class ResolutionContextStore:
    def commit(self, binding: ResolutionBinding, *, now: int) -> None: ...
    def lookup(self, synthetic_address: str, *, now: int) -> ResolutionBinding | None: ...
```

The store is bounded, keyed by both synthetic addresses, copies immutable
values, rejects conflicting live bindings, and fails closed at capacity.
Expiration removes forward and reverse references atomically. Origin state is
available only to trusted internal consumers.

```python
LegacySnapshotProvider = Callable[
    [LegacyOriginRequest, int],
    LegacyDnsSnapshot,
]


class NameNode:
    def resolve(
        self,
        presentation_name: str,
        *,
        now: int,
    ) -> NameResolution: ...
```

The constructor injects registry, legacy policy map, snapshot provider,
candidate validator, legacy cache, synthetic pool, context store, source-edge
identity, ID source, and maximum RouteIntent lifetime.

## Classification and resolution rules

1. Normalize the presentation name with the frozen canonical-name rules.
2. Check whether the name is configured as an NBSR service.
3. If configured, require a valid signed ServiceRecord. Signature, `kid`,
   validity, sequence, and revocation failures return the specific frozen
   `ProtocolViolation`; legacy fallback is forbidden.
4. Otherwise check a configured `LegacyServicePolicy`. DNS alone cannot create
   this policy or service identity.
5. If neither exists, return `NBSR_E_NAME_NOT_FOUND`.
6. For legacy policy, request a snapshot through the injected provider and
   apply it through `LegacyOriginCache`. Only an accepted `LegacyOriginView`
   may supply internal reachability.
7. Allocate or reuse a mapping from `SyntheticAddressPool`. The required
   lifetime is the shorter of policy/record validity and the 300-second
   RouteIntent maximum.
8. Create a RouteIntent with injected 16-byte route and lease IDs and a
   SHA-256 Resolution Context digest. The accepted record/policy sequence and
   policy hash are bound exactly.
9. Commit the immutable ResolutionBinding only after every prior operation
   succeeds.
10. Return `NameResolution` containing only the synthetic pair and route ID.

A failed refresh does not replace a valid mapping or binding. Approved
last-known-good behavior remains entirely inside `LegacyOriginCache`.
Authenticated negative answers, DNSSEC bogus/downgrade, policy failure,
rollback, equivocation, record revocation, and capacity failure prevent new
use immediately.

## Resolution Context

The Resolution Context ID is 32 random bytes from an injected cryptographic ID
source. Only its SHA-256 digest appears in RouteIntent. The raw context ID is
stored in the private `ResolutionBinding.resolution_context_id` field and is
not returned through DNS, logs, metrics, or errors.

Route and lease IDs are independent 16-byte values. Tests inject fixed,
distinct values and prove that reuse, truncation, boolean substitution, or
wrong lengths fail before commit.

## Synthetic mapping lifecycle

WP2A reuses `SyntheticAddressPool`; it does not choose a universal production
prefix. Prototype defaults remain loopback IPv4 and the existing generated
ULA profile, both configurable and collision-checked.

The name-to-synthetic mapping is independent of:

- DNS TTL;
- OriginSet sequence or endpoint membership;
- RouteGrant lifetime;
- transport-session lifetime; and
- application-stream lifetime.

An internal origin refresh MUST preserve the live Synthetic IP mapping.
Pool exhaustion returns `NBSR_E_HANDLE_EXHAUSTED` and MUST NOT reveal or fall
back to an origin address.

## DNS-compatible boundary

`NameNodeDnsAdapter` implements the `Callable[[str], ClientRoute]` boundary
already consumed by `DnsStub`. It derives `route_binding` from the RouteIntent
route ID and uses only the bounded NameResolution lifetime. It cannot access
or serialize the binding's internal OriginSet.

The optional lab listener:

- binds only an explicitly configured loopback address by default;
- supports UDP DNS and TCP DNS two-byte length framing;
- enforces maximum request size, one question, IN class, and A/AAAA types;
- returns only synthetic A/AAAA records;
- maps malformed input to FORMERR, unsupported questions to NOTIMP, missing
  names to NXDOMAIN, and security/internal failures to SERVFAIL;
- has bounded worker count and request timeout; and
- does not perform public recursion itself.

The injected snapshot provider remains deterministic in tests. A real
recursive/DNSSEC provider requires a separate approved design.

## Error handling

No new numeric error code is introduced. Internal failures map to existing
Core v0.1 errors:

| Failure | ErrorCode |
|---|---|
| Invalid name | `NBSR_E_NAME_INVALID` |
| No configured service | `NBSR_E_NAME_NOT_FOUND` |
| Invalid signature or owner trust | `NBSR_E_RECORD_UNTRUSTED` |
| Stale record, revocation, or origin state | `NBSR_E_RECORD_STALE` |
| Active record revocation | `NBSR_E_RECORD_REVOKED` |
| Missing internal resolution context | `NBSR_E_CONTEXT_REQUIRED` |
| Synthetic pool or context-store capacity | `NBSR_E_HANDLE_EXHAUSTED` |
| Legacy reachability unavailable | `NBSR_E_ORIGIN_UNAVAILABLE` |
| Unsupported internal profile | `NBSR_E_PROFILE_UNSUPPORTED` |

Unexpected exceptions are converted at the boundary to the non-sensitive
`NBSR_E_INTERNAL` fallback. Client-visible text never contains origin data,
trust-store paths, keys, DNS answers, or internal identifiers.

## Privacy-safe observability

The core emits typed local events to an injected sink. Event fields are:
event kind, classification, result code, bounded duration bucket, hashed
service audit ID, and capacity bucket. Raw names are disabled by default.
Origin names, addresses, endpoint counts tied to a name, raw Resolution
Context IDs, route IDs, lease IDs, keys, signatures, and payload bytes are
forbidden.

Operational counters may track aggregate successes, failures, cache freshness,
capacity, and latency. The design does not select a logging backend or
retention system.

## Test strategy

All implementation tasks use TDD and deterministic fakes.

Required suites:

- signed registry acceptance, owner `kid` binding, stale sequence,
  revocation-generation tombstones, wrong target, invalid time, and atomic
  failure;
- NBSR and legacy classification with no security downgrade;
- every successful A/AAAA resolution returns only a Synthetic IP;
- no direct origin fallback on pool exhaustion, DNS failure, bad signature,
  revocation, or unavailable route state;
- stable synthetic mapping across accepted legacy OriginSet refresh;
- DNS TTL, OriginSet validity, RouteIntent expiry, and mapping lifetime remain
  distinct;
- bounded store capacity and exact expiry behavior;
- origin and secret leakage scans across result objects, DNS bytes, events,
  exceptions, and logs;
- deterministic UDP/TCP loopback DNS tests with no public network;
- full existing suite, Ruff, OPA, Compose, vector reproducibility, and frozen
  registry/schema tests.

## Human gates preserved

This approval does not decide:

- production Synthetic IP prefix;
- real recursive resolver library or DNSSEC requirement/downgrade policy;
- Web PKI requirement level and health-check trust model;
- production persistence or HA staleness;
- native OriginSet schema, wrapper, message, or publisher authority;
- Name Node deployment on Windows/OpenWrt;
- WP3 transport, RouteGrant issuance, or Service Channel behavior; or
- production timeout, cache, quota, and retention values.

Implementation MUST stop if any task requires one of these choices or any
change to D1–D7.

## Exit criteria

WP2A core is complete only when:

- signed local records and revocations fail closed;
- all successful configured-name resolutions return synthetic addresses;
- invalid NBSR records never downgrade to legacy;
- origin reachability remains internal;
- RouteIntent and Resolution Context state are bounded and immutable;
- mapping remains stable across internal origin refresh;
- lab UDP/TCP DNS works without public DNS;
- all existing tests remain green; and
- status documentation still labels real recursion, WP3, federation, HA, and
  production deployment as unimplemented.
