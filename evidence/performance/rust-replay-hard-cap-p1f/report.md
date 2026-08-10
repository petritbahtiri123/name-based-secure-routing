# P1F Rust replay-history hard-cap report

Outcome A. The Rust destination retains exact Transport-Session replay history and rejects an otherwise-valid fresh stream with `OverCapacity` once the configured committed cardinality is reached. Duplicate and authorization failures retain precedence, rejection does not mutate replay state, and the pre-existing audit-before-commit transaction keeps audit failure from consuming capacity.

The 10,000-entry adversarial proof submitted 20,901,003 additional unique valid opens over 600 seconds. Every logical sample reported exactly 10,000 entries and HashSet capacity 14,336. The destination test remained alive and exited normally; the process exit dropped the owner. There was no prepared open after the boundary, so no upstream connection or application payload path was reachable.

Five paired 30-second warm-up/60-second measurement cells were required because the first BEFORE p99 contained a scheduler/backlog excursion. Median throughput was unchanged at 1,265.617 requests/s. Median p99 improved from 510,789 ns to 480,032 ns. Median destination CPU moved from 2.499% to 2.464%. All 759,370 measured requests succeeded and unexpected errors were zero.

The 601-second process trace recorded 560 samples. Private bytes moved from 11,956,224 to 13,168,640 bytes with a 15.55 B/s fitted slope; working set moved from 43,544,576 to 51,187,712 bytes with a 2,967 B/s fitted slope. Neither followed the 20.9-million rejected-attempt count, while replay entries and retained capacity were exactly flat. This supports the resource-safety classification `HARD_BOUNDED`; it is not a claim of seamless availability or allocator-level byte accounting.

Production Go active/standby session rotation remains absent. Reaching the selected hard cap can interrupt new stream creation until a fresh Transport Session is established.
