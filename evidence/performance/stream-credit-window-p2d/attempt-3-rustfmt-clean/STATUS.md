# Attempt 3 status

This is valid bounded-replay evidence produced against the rustfmt-clean
source and exact rebuilt binaries. It is **not the final acceptance authority**
because strict all-target Clippy subsequently found five benchmark-only
`too_many_arguments` warnings. The warnings did not identify a protocol,
security, or runtime failure, but fixing them changed benchmark source bytes.

Correction 3 mechanically grouped benchmark helper parameters into private
structs, then passed focused tests, rustfmt, and strict Clippy. Attempt 4 reran
the complete required ladder against that source, but later security and
source-binding corrections required new source freezes. Attempts 4-6 are
superseded or rejected. Attempt 7 is the sole authoritative final-source
acceptance campaign.
