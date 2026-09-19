# Repeat-qualified native namespace packet accounting

Twenty release fixed-work cells complete: five counterbalanced Direct/NBSR
pairs each for 1 KiB/64 streams and 16 KiB/eight streams. Source ec255c18;
1000 operations per stream, depth one, zero warmup. Every peer pair and full
cohort verifies. Every capture has observed bracketing markers, no reported
loss, exact tuple accounting and IP lengths within observed MTU 1500.
Independent TShark packet counts and IP-byte sums match each native analysis.
The prior disk-limited attempt remains separately INVALID_PARTIAL and is not
pooled, replaced or omitted. This new design was declared before launch.

Only tx-udp-segmentation is off on the two disposable private Docker veths;
GRO stays off and GSO/TSO on, with per-cell inventories and final restoration.
This is measured whole-flow native namespace accounting, including setup,
untimed validation, ACK and teardown. Marker packets are excluded. Incremental
Direct/NBSR differences include packetization and transport behavior; generic
UDP/IP/QUIC bytes are not called an NBSR tax. Positive or negative individual
results remain in paired-accounting.json, without selecting favorable repeats.

PARTIAL overall: phase separation, socket/process flow ownership, physical NIC
and wire validation remain unproven. Capture timing is DIAGNOSTIC only, never
stable throughput or speedup. This does not close the whole external matrix,
admission attribution, sustained soak or final funding freeze.
