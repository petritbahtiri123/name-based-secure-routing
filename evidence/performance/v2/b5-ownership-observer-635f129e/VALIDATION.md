# Optional continuous ownership preparation

Base 635f129e. Added source-global one-second callback observation, checked
destination sampler outcome, bounded controller tails/history and separate
coverage qualification. No live observer result or long soak exists at this stage.
The predeclared policy is docs/benchmarks/B5_OWNERSHIP_OBSERVER.md.

Literal source/destination observer RED logs retained. GREEN: source two tests,
destination one test, affected Rust B5 suite 45 PASS with one deliberately ignored
isolated timer diagnostic; release Clippy on all three peers with -D warnings and
Rust 2024 formatting PASS. Parent focused Rust review found no Important issue.

Python literal missing-module RED followed by nine tests PASS. Integration RED
proved missing observer/poll plumbing; a real-file replacement fixture was not
valid on Windows because open-file replacement is denied, so its corrected
identity-substitution RED is separately retained. Final ownership/controller
suite: 29 PASS. Ruff and diff checks PASS. Independent focused Python review found
no Important issue. Original external logs remain C:/NBSR-build; canonical copies
normalize line endings and whitespace.

Counters are exact integers; every role and local time coverage are required.
Three increasing medians are an early sampled-growth abort, not a leak claim.
Final all-eleven-zero close reports remain separate. Off/on observer comparison,
fresh thirty-second-window trials and long repeated near-ceiling soaks remain pending.
