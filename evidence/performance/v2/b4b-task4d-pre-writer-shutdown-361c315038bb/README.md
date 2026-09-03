# Superseded Task 4d draft run

This complete 34-repeat run used the first coordinator draft. A focused regression test later proved that `spawn_blocking(join)` could delay Tokio runtime shutdown beyond the evidence-writer deadline. The final implementation uses an in-memory writer completion signal and joins only a finished writer.

These raw measurements are preserved but are not the final current-binary evidence. Use `../b4b-task4d-361c315038bb/` instead.
