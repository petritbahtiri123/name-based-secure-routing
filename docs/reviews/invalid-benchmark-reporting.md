# Invalid and empty benchmark reporting

P2A cells without valid repeats emit null median/CV values and retain repeat and
error counts. An empty campaign is not accepted. Mixed cells summarize only
valid repeats; campaign acceptance still rejects any invalid repeat.
Manifest and analysis CV values use the same valid-repeat population. The
existing selective-rerun decision still uses raw repeat CV; workload selection
has not changed.

P2B zero-success shards emit null latency rather than StatisticsError. Aggregate
summaries retain every shard, error, elapsed time and CPU usage; successful
shards alone contribute latency values. No completions means null per-operation
latency and CPU values, not zero. The existing median-of-shard-quantiles method
is unchanged. This does not change transport, validity, pacing or lifecycle.
Legacy downstream profile interpretation still requires valid measured data;
these summaries are failure evidence, not accepted performance results.

The 11 synthetic cases in tests/ci/test_invalid_benchmark_reporting.py are
selected by existing python-core tests/ci. Build/peer/authority/resource
boundaries are mocked; writes stay in pytest temporary directories. Tests cover
all-invalid, mixed, normal and empty P2A reports; failed/mixed/normal P2B shards
and aggregates; and preservation of failed P2B raw summaries. No VM, network,
Rust build or workload is executed.

Independent neighbor testing exposed a pre-existing fixture mismatch: the P2A
resource-summary fixture omitted the required thread_count sample field. The
fixture now includes it and asserts the measured peak excludes the warmup peak.
Both existing P2A/P2B neighbor files are selected in the same python-core change;
a regression asserts their selection. This fixture correction does not weaken
production sampling requirements or change runtime code.
