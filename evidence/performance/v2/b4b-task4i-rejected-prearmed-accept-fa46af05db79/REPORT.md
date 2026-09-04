# Task 4i preliminary campaign — REJECTED

**INVALID FOR CAPACITY.** The destination benchmark pre-created all 512
`accept_one()` futures, starting their unchanged five-second listener deadlines
before rate-controlled clients were scheduled. At 25/s this admitted about 125
clients and expired the remaining accepts before their client attempts began.

The raw 25/s and 50/s runs are retained as regression evidence for this harness
defect. They are excluded from Task 4i capacity classification and from every
sustainable-rate claim. No raw record was edited.
