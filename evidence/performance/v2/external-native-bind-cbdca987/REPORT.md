# Benchmark-only native IPv4 placement

MEASURED functional/security diagnostics; external hardware NOT_RUN.

The old benchmark source and listeners were fixed to loopback. A feature-gated
local IPv4 bind option now enables preparing a native two-host test. Direct and
NBSR preserve their default loopback addresses. The default production connect
API and authentication body are unchanged; only benchmark-harness exposes the
new entry. No protocol, wire, authority, crypto, replay, admission, ACCEPT or
ACK/send-completion semantic change, and no performance optimization claim.

Source accepts concrete IPv4 with port0. Listener accepts a concrete IPv4 and
fixed or kernel-assigned port. Invalid/duplicate/wrong-role/unspecified/multicast/
limited-broadcast/IPv6 inputs reject; explicit listener and capture-port override
conflict. The separate source lifecycle harness rejects unsupported explicit
bind use rather than ignoring it. Directed-subnet broadcast needs netmask context
and is not guessed from address spelling.

Literal RED parser/export failures precede implementation.36 focused parser,
transport/security and UDP tests pass. Release three-binary Clippy -Dwarnings
and parent cargo fmt --check pass. Nonbenchmark library/three-bin compile passes
with pre-existing warnings retained; it is not a no-feature Clippy-clean claim.
The parent reviewed all changed source/test files once and found no Important
or Critical correctness/security issue. Eight raw tested source snapshots match
the committed candidate bytes.

Four local live diagnostics pass: Direct/NBSR with default127.0.0.1 and explicit
127.0.0.2. Listener readiness and actual owned-source UDP endpoints prove the
chosen address. All source/server processes exit0 and join; all four NBSR final
reports show11 zero current counters. These are address/cleanup diagnostics,
not a throughput comparison or real external-interface/server result.

The accompanying native Linux two-host runbook has11 Bash syntax checks and5
Python AST checks. Remote execution remains NOT_RUN, and the complete portable
admission/memory/soak/wire matrix remains PARTIAL. Authored finite commands do not
establish Task8 full acceptance. The runbook preserves the existing Direct30s
completion ACK budget and documents that the current single-group NBSR branch
does not wait for that marker.

Raw79-file manifest and actual-byte hash are in parent-review.json. Private
one-day test authority fixtures remain outside the repository; only checksums
and selected non-secret logs/records are copied here. Canonical text is normalized
and independently checksummed. The tested patch is bound by raw source copies,
base SHA and the implementation commit, not a fabricated clean-run source claim.
