# P1/P2 Repository Gate Failure Classification

## Result

A fresh detached checkout at `55ada9f` with global `core.autocrlf=true` proved
that the repository-owned LF policy fixes the byte-conversion cluster without
rewriting frozen artifacts. Core v0.1 vector generation, Go dependency
inventory, and WP4 exporter-vector verification each passed independently.

The remaining representative failure is a real authority mismatch: the frozen
Core baseline plus F75 overlay does not authorize four later P1/P2 source
digests. No validator, frozen authority, or positive test was changed.

| Cluster | Representative result | Classification | Required action |
|---|---|---|---|
| Checkout byte conversion | checkout-policy test RED then GREEN | Fixed | Keep explicit LF attributes |
| Core v0.1 vectors | 1 passed | Resolved by fresh checkout | No vector rewrite |
| Go dependency inventory | 1 passed | Resolved by fresh checkout | No dependency rewrite |
| WP4 exporter vectors | 1 passed | Resolved by fresh checkout | No vector rewrite |
| Core/F75 current-tree validation | 1 failed at `admission.rs` | Authority conflict | Explicit approval required |
| Windows wire build | Not rerun in this classification step | Environment gate | Use external prebuilt target |

## Exact authority delta

The closed delta contains exactly:

- `crates/nbsr-transport/src/admission.rs`: 33,115 bytes, SHA-256 `161664bf2cb7ba512cb28bea0acd5a394bf6eb82ebd2fbf80b3546ccf157802c`
- `crates/nbsr-transport/src/lib.rs`: 6,634 bytes, SHA-256 `c3dd27a6b11a53e53f1fcb7cce1b0b3f52c4c616c9c70f07d281d435022c6d3e`
- `crates/nbsr-transport/src/quinn_adapter.rs`: 69,112 bytes, SHA-256 `af932da98d9309b0741b2f20b78831a429e20184898ed48646702210736cbda7`
- `crates/nbsr-transport/src/session.rs`: 71,569 bytes, SHA-256 `fb1d44e226cd208ef9a37879f4da7174e4be8c21d0d999071f2b7e2cd56d7248`

The frozen baseline digest remains
`21d60dc60ee1bc00bef882b63fabaaea9229768770912ed7c93e6ae4d54453ef`.
The current parent F75 overlay digest is
`e095efd18e2d6ca154bfa5c49ae4e41362856e5054349040ca20ddc151c9ab1a`.

`core-v0.2-p1p2-overlay.candidate.json` records these values but is explicitly
`CANDIDATE_NOT_AUTHORITY`. Activating it requires separate approval of the four
paths, their exact bytes, parent binding, and fail-closed validator semantics.
