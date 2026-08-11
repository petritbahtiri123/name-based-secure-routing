# Attempt 2 status

This is valid bounded-replay evidence produced after correction 1, and every
recorded endpoint used replay limit 10,000. It is **not the final-source
acceptance authority** because `cargo fmt` subsequently changed source bytes.
No semantic change was identified, but the exact measured source binding no
longer matched the rustfmt-clean final files.

Correction 2 reran the complete required ladder as attempt 3 against the exact
frozen final source and rebuilt release binaries. Attempt 3 is the sole
authoritative final acceptance campaign. Attempt 2 remains unchanged except
for lossless deterministic compression of its oversized soak and this status
record.
