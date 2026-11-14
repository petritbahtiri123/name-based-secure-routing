# ACE canonical-name parity diagnostic, 2026-11-14

## Scope and outcome

Read-only runtime investigation; no route, signed-object, dependency, registry or
trust-policy change. The accompanying `2026-11-14-ace-parity-observed.json`
records 20 bounded predicate cases, exact source SHA-256 values, helper hash,
compiler/Python versions, and current HEAD. This is not an end-to-end signed
admission test, vulnerability exploit, exhaustive name-space proof, or permission
to enable registration/READY.

The actual native `valid_canonical_name` body was extracted verbatim from
`crates/nbsr-transport/src/federation.rs:372`, compiled with the installed rustc
using only std, and called with the same strings as the actual Python functions
`nbsr/federation/ownership.py:25::_canonical_name` and
`nbsr/federation/fields.py:104::_delegation_scope`. Extraction requires exactly
one matching function; the hash identifies the body. No rewritten Rust predicate
was used. Owned subprocesses were bounded to 95 seconds with process-tree cleanup
on timeout; run completed under one second. No Cargo, sockets, keys or VM work.

Python ownership and scope agreed on all 20 cases. Native predicate differed on:

| Name | Python ownership/scope | Native predicate |
| --- | --- | --- |
| `xn--a.example` | reject | accept |
| `xn--fa-hia.example` | reject | accept |

`xn--bcher-kva.example` is accepted by all three. Native currently checks LDH,
ASCII/lowercase and lengths but not ACE decode/re-encode validity. The latter
mismatch is edition-sensitive and must not be treated as proof that Python's
acceptance policy is the intended normative IDNA policy.

Additional coverage: uppercase, Unicode presentation name, empty label, trailing
dot, leading/trailing hyphens, underscore, 63/64-byte labels, total253/254/255/256
bytes, and an IP-shaped string. The 256-byte case keeps every label <=63 bytes,
so total-length rejection is not masked by a too-long label.

A misleading existing negative is worth noting: `xn--invalid.example` is accepted
by both Python name functions and the native predicate. The ownership test in
`tests/federation/test_ownership.py:68` replaces the name without recomputing the
service ID; its rejection therefore does not isolate malformed-ACE validation.
This diagnostic does not change that existing multi-field negative test.

## Intended contract and unresolved choice

`docs/protocol/wp8-federation-v0.1-schema-requiredness.md:49` requires lowercase
NFC A-label form, <=255 encoded bytes; the schema registry repeats this. These
sources do not select IDNA2003, IDNA2008 or UTS46. Python's implementation uses
the standard-library `idna` codec (RFC3490), which is an implementation choice,
not a documented cross-language standard amendment.

Do not silently borrow Core's distinct <=253-byte/no-IP-literal contract from
`docs/protocol/core-v0.1-wire-schema.md`. All three tested federation predicates
accept the IP-shaped string and 254/255-byte names; that observation does not
settle overall protocol acceptance of those names.

The native helper is used at `federation.rs:152` in the authorization binding
validation path, alongside independent authority/binding checks. A name predicate
acceptance alone cannot bypass those checks or establish a forged authorization.

## Safe next options

1. Preserve current runtime behavior. Reuse this corpus as observed evidence
   while the genesis-only test adapter is limited explicitly to ordinary LDH
   non-ACE names. ACE inputs must be reported unsupported by that slice, not
   globally invalid. This is the smallest non-normative implementation path.
2. If full parity is required, first record the supported federation IDNA profile
   and edition-sensitive compatibility decision. Then use a reviewed, bounded
   implementation with exact positive/negative cross-language vectors. Do not
   normalize or repair signed canonical-name bytes after signature verification.
3. A future transition to a different IDNA profile must treat existing service-ID
   derivation and signed ownership/scope identity compatibility explicitly; do
   not simply add a modern IDNA dependency and assume equivalent acceptance.

Independent read-only review confirmed the diagnostic method and contract caveat.
No production fix, whole-crate test, hosted CI, route behavior or live governance
claim accompanies these results. Existing normal3/5, emergency2/5 and all
applicable controller requirements remain unchanged.
