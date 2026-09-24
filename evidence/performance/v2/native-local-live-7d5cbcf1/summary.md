# Native local live-guard prerequisite

Implementation: 7d5cbcf149b99e3c71365c885c4d532208e1148b.
COMPLETE: bounded host-local helper and synthetic regression verification.
NOT YET PROVEN: runtime integration, observer neutrality or sustained capacity.

Thirteen literal RED tests preceded implementation. Review identified late
resource delivery inflating apparent evaluated coverage; an additional literal
RED reproduced it. Only samples passed to the existing growth predicate now count.
Final 68 affected tests and Ruff PASS; focused independent review and scoped
re-review clean. Test logs/checksums retained through raw-evidence.json.

Commands:

```powershell
python -m pytest tests/performance/test_linux_native_live.py tests/performance/test_linux_native_paced.py tests/performance/test_b5_stream.py -q
python -m ruff check scripts/performance/linux_native_live.py tests/performance/test_linux_native_live.py
```

All data are SYNTHETIC diagnostic correctness fixtures, not benchmark statistics.
No production, timeout, protocol or security change. Uses existing drift/growth
thresholds. Phase timing is approximate local receipt minus source elapsed time;
never compare two hosts' monotonic clocks. Current APIs do not yet connect this
helper to native peers. Full native paced integration and validation remain open.
