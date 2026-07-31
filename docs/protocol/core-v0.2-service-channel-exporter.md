# Core v0.2 Service Channel exporter profile

Status: frozen conformance profile for WP4. This document defines deterministic
context bytes and fixture-secret test vectors. It does not claim or implement a
live rustls, Quinn, or TLS-handshake exporter call.

## Profile constants

- Exporter output length: 32 bytes.
- Hash and HMAC: SHA-256.
- Exporter label, as ASCII bytes: `EXPORTER-NBSR-Service-Channel-v2`.
- Context profile string: `NBSR-SERVICE-CHANNEL-CONTEXT-v2`.

## Canonical context

The exporter context is a deterministic, preferred-serialization CBOR array.
It has exactly 14 items in the following order. No tag, indefinite-length item,
non-preferred integer/length encoding, trailing byte, alternate type, or
additional item is accepted.

| Index | Value | CBOR type and constraint |
| ---: | --- | --- |
| 0 | `NBSR-SERVICE-CHANNEL-CONTEXT-v2` | text string, exact |
| 1 | `2` | unsigned integer, exact |
| 2 | `session_id` | byte string, exactly 16 bytes |
| 3 | `source_edge_id` | text string, 1..64 ASCII bytes |
| 4 | `destination_edge_id` | text string, 1..64 ASCII bytes |
| 5 | `channel_id` | byte string, exactly 16 bytes |
| 6 | `route_id` | byte string, exactly 16 bytes |
| 7 | `route_grant_digest` | byte string, exactly 32 bytes |
| 8 | `service_id` | text string, 1..255 ASCII bytes |
| 9 | `transport` | text string, exactly `tcp` or `udp` |
| 10 | `port` | unsigned integer, 1..65535 |
| 11 | `policy_hash` | byte string, exactly 32 bytes |
| 12 | `client_nonce` | byte string, exactly 32 bytes |
| 13 | `edge_nonce` | byte string, exactly 32 bytes |

All context constraints are checked before derivation. The context hash is:

```text
context_hash = SHA-256(canonical_context_bytes)
```

## TLS 1.3 derivation

The conformance vectors begin with an explicit, fixed 32-byte
`exporter_master_secret`. They apply RFC 8446 `HKDF-Expand-Label` semantics:

```text
empty_hash = SHA-256("")
derived_secret = HKDF-Expand-Label(exporter_master_secret,
                                  "EXPORTER-NBSR-Service-Channel-v2",
                                  empty_hash,
                                  32)
exporter_value = HKDF-Expand-Label(derived_secret,
                                  "exporter",
                                  context_hash,
                                  32)
```

For each invocation, `HKDF-Expand-Label(secret, label, context, length)` uses
HKDF-Expand with HMAC-SHA-256 and this `HkdfLabel` encoding:

```text
uint16(length) ||
uint8(len("tls13 " || label)) || "tls13 " || label ||
uint8(len(context)) || context
```

An output length that does not fit `uint16`, or a prefixed label/context length
that does not fit its `uint8`, is rejected. This profile additionally rejects
any exporter label other than the exact profile label and any output length
other than 32 bytes.

## Conformance package

`vectors/core-v0.2/wp4-exporter/manifest.json` is the closed, versioned package
index. Every referenced artifact path is package-relative and carries its byte
length and SHA-256 digest. The package contains two valid vectors and 21
invalid/mutation cases. The cases cover each context-array item, array order,
CBOR type, fixed lengths, preferred CBOR encoding, label, output length, and
master-secret separation.

The Python generator regenerates fixtures deterministically. Its `--check`
mode builds a package in a temporary directory and compares all checked-in
files byte-for-byte without rewriting them. The Node.js verifier independently
checks the closed manifest, artifact digests, bounded preferred CBOR, both
HKDF steps, declared rejections, and separation cases without invoking or
importing the generator. Rust consumes only checked-in fixture bytes for pure
conformance derivation.

These fixtures do not expose a production secret API, do not add a live TLS
exporter invocation, and do not change admission, stream, origin, lifecycle,
resume, UDP, or Core v0.1 behavior.
