# Windows benchmark interval overflow

Bounded correctness follow-up to the Linux benchmark-clock port. The existing
Windows QPC conversion multiplies signed ticks by1e9 before division. Measured
host QPC frequency is10000000Hz. A synthetic two-hour starting tick makes the
actual Go Since implementation return-178697629283ns instead of approximately
7200000000000ns. Literal RED is retained in checkpoint-20260925-final/clock-red.txt.
No two-hour wall-clock run is implied.

Smallest correction: widen only the intermediate product using standard-library
math/bits.Mul64 and Div64. Preserve integer precision, signed intervals and the
existing QPC source. No transport, authentication, wire, timeout or deadline
change. The internal benchmark clock is not production protocol time authority.
Conversion remains subject to the representable signed nanosecond duration range.

GREEN covers zero, short, fractional, two-hour positive/negative, high-frequency
and signed-int64 endpoint cases. Existing sub-millisecond test remains unchanged.
Go interop race suite and vet pass; focused independent review is clean. Earlier
short-workload evidence remains bound to its own binaries; no performance gain,
long-soak pass or new stable capacity is claimed from this correctness repair.
