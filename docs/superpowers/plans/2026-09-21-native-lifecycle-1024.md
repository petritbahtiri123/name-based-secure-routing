# Native lifecycle 1024-bundle bounded extension

Execute inline with the existing autonomous authorization and remaining weekly
budget (absolute ceiling 27% used; checkpoint before it). This is a finite B3/B4
functional scale experiment, not a stable admissions/throughput claim.

## Evidence and design

- At 3dfd9f8a the automated private-stream coordinator completes five fresh
  namespace cells of 512 bundles at 100 offered/s, exact ACKs and zero final
  ownership. Its six EOF cancellation cases also pass.
- The existing release Rust lifecycle parser already allows up to 1024 clients
  without keepalive. The Python command/parser/barrier/ledger/pair gates stop at
  512. Extending that explicit benchmark bound requires no Rust/Go change.
- The destination policy's existing idle lifetime is ten seconds. At 100/s,
  1024 launch slots span 10.23 seconds before the two-second hold; do not call
  that scheduling incompatibility a production limit or increase the timeout.
- Declare a **new** 200 offered/s workload for matched 512 and 1024 cells. The
  ideal 1024 launch span is 5.115 seconds, leaving room for the unchanged hold.
  This is not a substitute for prior 100/s results or a sustained-rate claim.
- Keep two shards, one selected guest CPU per role, 1 KiB materialized payload,
  native local TLS/control/output, fresh namespaces and every existing gate.
- 1024 source markers plus releases/ACKs remain below the existing 10,000-entry
  collection bound; socket inventory remains below its 8,192-FD scan bound.

## Steps

1. Literal RED tests for 1024 command/config/parser/complete barrier acceptance,
   and rejection of missing clients. Retain rejection of 2048 and bool counts.
2. Share the bounded cardinality list across Python layers and add 1024 only.
3. Focused tests, Ruff/diff, one focused review; atomic implementation commit.
4. Build exact-SHA release peers; verify unchanged Rust binary hashes.
5. Five declared repeats per 512/1024 cell at 200/s, counterbalanced order.
   Preserve every failed cell. Stop the cohort on cleanup failure or low disk;
   do not replace unfavorable outcomes. No simultaneous benchmark campaigns.
6. Analyze raw cardinality/hold/ACK/ownership, process resources and failure
   observations. Timing remains diagnostic; retain earlier failed cohorts.
7. Seal evidence, integrity/privacy checks, atomic evidence/checkpoint commit.

If progress fails despite resource headroom, record the actual delayed phase and
profile before any optimization. No keepalive, transport timeout, protocol,
security, release/ACK or assertion relaxation is authorized by this extension.

## Result

Complete at 3c3f784a: three RED failures, 112 focused tests GREEN, exact release
rebuild with unchanged Rust hashes. Five counterbalanced cells at each of 512
and 1024 complete all clients, ACK/hold/cooldown and eleven zero ownership fields.
The independent analysis and raw checksum package retain all ten cells. Median
held RSS is 199.125/164.25 MiB at 512 and 384.5/320.5 MiB at 1024 for the two
roles. The compound paired RSS slope is 681.75 KiB per extra bundle, not separate
object allocation. Handshake p99 remains highly dispersed (~1.03 seconds at
1024), so no latency-stable or sustained-admission claim follows.
