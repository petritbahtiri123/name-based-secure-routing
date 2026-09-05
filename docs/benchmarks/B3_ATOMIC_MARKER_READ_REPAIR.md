# B3 materialized marker read repair

Measured failure: `b3-materialized-streams-797aabf1/raw/rust-rust/streams-8-r3`
failed before active sampling with PermissionError13 while reading the published
`destination-0.active` marker. Source/destination stderr had no transport failure.
The two preceding valid runs and this invalid harness attempt remain retained;
all34 raw hashes verified. This is not a stream-capacity result.

Previously the harness waited for existence and then read the marker once.
The new helper waits for readable atomic JSON inside the SAME120-second deadline.
Missing/sharing-denied reads retry at the existing10ms cadence, clipped to the
remaining deadline. Parsed markers are cached; polling stops at the first
unreadable marker to avoid repeatedly opening every pending path. Malformed JSON
and failed child processes still fail. No timeout, hold, payload or protocol
change was made. Permanent access denial still exhausts the original gate.

Literal RED: four focused tests failed because wait_json_paths was absent.
GREEN: transient permission retry, shared deadline, malformed JSON and failed
child tests pass, alongside affected B3/lifecycle tests (15 total). Scoped Ruff
and diff checks pass. One focused independent review found no Important findings.
Fresh live materialized-stream repeats follow this commit; existing bad evidence
is not overwritten or silently replaced.

Separate512-bundle failures are NOT repaired by this change. At100/s, all512
materialized handles were reported but46 early clients failed completion. At125/s,
one diagnostic and three scheduled repeats passed, then83 early clients failed.
These observations are consistent with the10-second destination idle bound but
do not prove last-packet timing or close reason. Retained handles do not prove a
still-open transport. Largest repeated successful bundle scale so far is256.
No512 stable-memory, leak, production-ceiling or hardware-ceiling claim follows.
