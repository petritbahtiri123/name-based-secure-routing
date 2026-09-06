import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location("driver", Path(__file__).with_name("driver.py"))
driver = importlib.util.module_from_spec(spec)
spec.loader.exec_module(driver)


def test_fixed_workload_has_no_ownership_or_capacity_claim():
    args = driver.controller_args(Path("cell"), Path("target"))
    assert args.diagnostic and args.paths == ["nbsr"]
    assert args.rate == [421624000000, 150013467]
    assert (args.cores, args.groups, args.payload, args.streams, args.depth) == (1, 1, 16384, 8, 1)
    assert (args.warmup, args.duration, args.progress) == (3, 120, 30)
    assert args.ownership_sampling is False


def test_repeat_expansion_and_observer_rejection():
    rows = [{"arm": a, "gbps": 1.0, "p99_ns": 100} for a in ("off", "on") for _ in range(3)]
    assert driver.comparison(rows)["observer_accepted"]
    rows[-1]["gbps"] = 1.5
    assert driver.comparison(rows)["required_pairs"] == 5
    for row in rows:
        if row["arm"] == "on":
            row["p99_ns"] = 106
    assert not driver.comparison(rows)["observer_accepted"]


def test_csv_schema_strips_hostname_and_rejects_missing_counter(tmp_path):
    import csv
    p = tmp_path / "data.csv"
    with p.open("w", newline="") as f:
        csv.writer(f).writerows([["time", *["\\\\SECRET_HOST" + c for c in driver.COUNTERS]], ["stamp", *["1.0"] * 6]])
    rows = driver.read_csv(p)
    assert len(rows) == 1 and "SECRET_HOST" not in str(rows)
    p.write_text('"time","wrong"\n"stamp","1"\n')
    with pytest.raises(ValueError):
        driver.read_csv(p)


def coverage_fixture():
    from datetime import datetime, timedelta, timezone
    start = datetime(2026, 9, 6, 12, tzinfo=timezone.utc)
    def a(seconds):
        return {"utc": (start + timedelta(seconds=seconds)).isoformat(),
                "monotonic_ns": seconds * 1_000_000_000, "local_utc_offset_seconds": 0}
    meta = {"before_launch": a(0), "after_launch": a(0), "ready": a(2),
            "before_stop": a(122), "after_join": a(123)}
    rows = [{"typeperf_local_timestamp": (start + timedelta(seconds=s)).strftime("%m/%d/%Y %H:%M:%S.%f")[:-3]}
            for s in range(1, 123)]
    return rows, meta


def test_coverage_accepts_contiguous_bounded_interval():
    rows, meta = coverage_fixture()
    assert driver.validate_coverage(rows, meta)["coverage_valid"]


@pytest.mark.parametrize("problem", ["duplicate", "stale", "gap", "clock", "offset", "format"])
def test_coverage_rejects_unsupported_interval(problem):
    rows, meta = coverage_fixture()
    if problem == "duplicate":
        rows[4] = rows[3]
    elif problem == "stale":
        rows = rows[:110]
    elif problem == "gap":
        del rows[5:9]
    elif problem == "clock":
        meta["before_stop"]["monotonic_ns"] += 10_000_000_000
    elif problem == "offset":
        meta["before_stop"]["local_utc_offset_seconds"] = 3600
    elif problem == "format":
        rows[0]["typeperf_local_timestamp"] = "2026-09-06 12:00:01"
    with pytest.raises(ValueError):
        driver.validate_coverage(rows, meta)
