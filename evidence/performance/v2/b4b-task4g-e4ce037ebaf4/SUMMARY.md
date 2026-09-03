# Task 4g observer results

PARTIAL / UNRESOLVED

| Clients | OFF admitted | ON admitted | OFF Gbit/s | ON Gbit/s | OFF admissions/s | ON admissions/s | Gate |
|---|---:|---:|---:|---:|---:|---:|---|
| 128 | 128 | 128 | 0.618359 | 0.638170 | 38.731 | 73.582 | REJECT |
| 256 | 237 | 226 | 0.598026 | 0.592558 | 44.176 | 41.516 | REJECT |

Intervals are pooled descriptive ON observations, not independent repeat medians. Rejected observer data cannot attribute the uninstrumented collapse.

ETW not collected. No handshake mechanism, scheduler cause, or production limit is claimed.

Reproduce: `python scripts/analyze_b4b_task4g.py --root <evidence-root>`
