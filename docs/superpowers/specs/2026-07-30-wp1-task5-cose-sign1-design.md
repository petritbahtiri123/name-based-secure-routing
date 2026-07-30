# WP1 Task 5 COSE Sign1 Design

**Status:** Approved design; implementation plan pending review  
**Date:** 2026-07-30  
**Branch:** `codex/nbsr-v3-wp0-wp1`  
**Scope:** Core v0.1 COSE Sign1 with Ed25519 only

## Objective

Implement the smallest Core v0.1 object-signature surface required by D2 and
D6-A3. The implementation signs deterministic CBOR payload bytes, verifies
them only against a caller-supplied trust context, and returns bounded,
non-sensitive protocol errors.

This task does not add a COSE dependency, change a frozen registry or schema,
generate vectors, integrate with the runtime, or implement WP2/WP3 behavior.

## Selected approach

Use the existing deterministic CBOR gate plus `cryptography` Ed25519
primitives. Keep verification context explicit:

```python
sign1(
    payload: bytes,
    kid: bytes,
    key: Ed25519PrivateKey,
) -> bytes

verify_sign1(
    message: bytes,
    keys: Mapping[bytes, Ed25519PublicKey],
    failure_code: ErrorCode,
) -> VerifiedSign1
```

`failure_code` accepts only:

- `NBSR_E_RECORD_UNTRUSTED` for ServiceRecord and Revocation; or
- `NBSR_E_GRANT_INVALID` for RouteGrant.

This avoids inferring object class from untrusted bytes. It also avoids
separate near-duplicate record/grant COSE parsers. An always-generic error was
rejected because it would lose the already-frozen object-specific failure
semantics.

`VerifiedSign1` is an immutable, slotted dataclass containing only:

- `payload: bytes`; and
- `kid: bytes`.

## Exact wire profile

The required outer item is canonical CBOR tag 18 followed by:

```text
[
  protected : bstr,
  unprotected : {},
  payload : bstr,
  signature : bstr
]
```

The decoded protected map is exactly:

```text
{
  1: -8,
  4: kid
}
```

Rules:

- tag 18 is required and uses its preferred one-byte representation;
- `alg=-8` and `kid` appear only in the protected map;
- `kid` is an opaque byte string of 1 through 64 bytes;
- the unprotected map is exactly empty;
- payload is attached and is a byte string;
- signature is exactly 64 bytes;
- external AAD is always the empty byte string;
- unknown, duplicated, critical, or unprotected headers are rejected;
- detached/null payloads and trailing bytes are rejected; and
- only `Ed25519PrivateKey` and `Ed25519PublicKey` objects are accepted.

The signature input is the deterministic encoding of:

```text
["Signature1", protected, b"", payload]
```

## CBOR boundary

The generic Core v0.1 deterministic decoder continues to reject every CBOR
tag. COSE support does not relax it.

`cose.py` handles only the exact preferred tag-18 prefix, then passes the
remaining Sign1 array and the protected-header byte string independently
through `decode_deterministic`. Encoding prepends the exact preferred tag-18
byte to a body produced by `encode_deterministic`.

This keeps duplicate-key, preferred-encoding, ordering, nesting, collection,
and byte-budget enforcement in the existing NBSR CBOR gate. No
`cbor2.dumps(..., canonical=True)` path is introduced.

## Trust and D6-A3 binding

Key lookup uses only `keys[verified_kid]` from the mapping supplied by the
caller. A `kid` has no global meaning and is never parsed as text, a path, or
an operator identifier.

After generic verification:

- a ServiceRecord payload is decoded and its `owner_key_id` must equal the
  verified `kid` byte-for-byte;
- a Revocation payload is decoded and its `issuer_key_id` must equal the
  verified `kid` byte-for-byte; and
- a RouteGrant is accepted only when its `kid` resolves inside the
  caller-supplied authorized RouteGrant-issuer trust context.

A small `require_kid(verified, expected_kid, failure_code)` helper performs
the two byte-for-byte payload bindings without learning object types.

RouteIntent, ProtocolError, and ControlEnvelope receive no object-level COSE
helper or wrapper in Core v0.1.

## Failure behavior

Verification converts malformed structure, unsupported profile, missing trust
entry, wrong key type, invalid signature, and `kid` binding mismatch into
`ProtocolViolation(failure_code, fixed_message)`.

The exception never includes:

- dependency error text;
- key material;
- payload bytes;
- signatures;
- trust-store contents; or
- internal filesystem or policy information.

Invalid local signing inputs fail with
`NBSR_E_PROFILE_UNSUPPORTED`; cryptographic library exceptions are chained
internally but are not included in the fixed peer-safe message.

Resource-limit failures remain `NBSR_E_OVER_CAPACITY` when raised by the
existing CBOR gate before object trust. This preserves the approved CBOR
resource-error mapping.

## Test design

Tests are written before implementation and cover:

1. deterministic valid signing and verification;
2. ServiceRecord and Revocation byte-for-byte `kid` binding;
3. RouteGrant lookup only inside the supplied authorized issuer context;
4. absence of object-level wrappers for the three unsigned D6 types;
5. missing, unprotected, duplicated, or non-EdDSA algorithm headers;
6. missing, malformed, empty, oversized, or duplicated `kid`;
7. missing/wrong tag, detached/null payload, nonempty unprotected map, and
   trailing bytes;
8. unknown protected/critical headers;
9. non-Ed25519 signing or verification keys;
10. tampered protected header, payload, and signature;
11. trust-context lookup miss;
12. caller-selected record/grant error mapping; and
13. preservation of `NBSR_E_OVER_CAPACITY` for CBOR resource limits.

Focused tests, the complete protocol suite, the full Python suite, Ruff,
`pip check`, and `git diff --check` must pass before commit.

## Compatibility and non-claims

Classification: internal Core v0.1 implementation of already-frozen D2 and
D6-A3 behavior; no new wire allocation.

The task does not:

- change the 17 message codes or 19 error codes;
- change any D6 numeric field mapping;
- add a critical extension, state, transition, or COSE wrapper;
- expose signing or trust decisions to the current runtime;
- generate or freeze Task 6 vectors;
- claim cross-language COSE agreement; or
- authorize WP2, WP3, federation, or production use.

## Acceptance gate

Task 5 is complete only when the exact tagged profile and all negative cases
pass with stable errors, the three D6-A3 signed-object rules are enforced, the
three unsigned object types remain unwrapped, and no existing runtime or frozen
protocol surface changes.
