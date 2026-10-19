import json
import pathlib
import tempfile
import unittest
from scripts.performance import linux_native_peer as peer
from scripts.performance.linux_native_paced import read_paced
from scripts.performance.sphere_support.paced_progress import Progress
from scripts.performance.sphere_support.paced_contract import Guard

HERE = pathlib.Path(__file__).resolve().parent


def cell(seconds=300):
    return dict(path="nbsr", cores=1, payload_bytes=1024, streams=2, outstanding=1, diagnostic_seconds=seconds, diagnostic_rate=[6000, 1])


def row(index=1, completed=6000, prior=0, duration=300):
    counts = dict(
        offered=index * 6000,
        reserved=completed,
        issued=completed,
        completed=completed,
        missed=index * 6000 - completed,
        unreserved_current=0,
    )
    samples = completed // 64 - prior // 64
    return dict(
        schema="nbsr-b5-grouped-progress-v1",
        event="b5_grouped_progress",
        window_index=index,
        phase="steady",
        elapsed_ns=index * 10**9,
        interval_start_ns=(index - 1) * 10**9,
        interval_end_ns=index * 10**9,
        issue_deadline_ns=duration * 10**9,
        **counts,
        group_counters=[dict(group_id=0, **counts)],
        goodput_bytes_per_second=(completed - prior) * 2048,
        sample_count=samples,
        sample_stride=64,
        sample_capacity=1000,
        max_reservation_lateness_ns=0,
        sample_overflow_count=0,
        errors=0,
        timeouts=0,
        evidence_valid=True,
        p50_latency_ns=100 if samples else None,
        p95_latency_ns=100 if samples else None,
        p99_latency_ns=100 if samples else None,
    )


class PacedTests(unittest.TestCase):
    def test_exact_single_progress_argument(self):
        argv, _ = peer.native_command(
            cell(),
            "source",
            pathlib.Path("/b"),
            pathlib.Path("/a"),
            pathlib.Path("/o"),
            bind="192.0.2.2:0",
            endpoint="192.0.2.1:4433",
            post_close_reports=True,
        )
        self.assertEqual(argv.count("--p2a-progress-seconds"), 1)
        for key, want in [
            ("--p2a-progress-seconds", "1"),
            ("--b5-rate-numerator", "6000"),
            ("--b5-rate-denominator", "1"),
            ("--p2a-duration-seconds", "300"),
            ("--p2a-streams", "2"),
        ]:
            self.assertEqual(argv[argv.index(key) + 1], want)

    def test_smoke_and_conflicting_duration(self):
        self.assertEqual(peer.measurement_contract(cell(20)), (3, 20))
        c = cell()
        c["operations_per_stream"] = 10
        with self.assertRaises(ValueError):
            peer.measurement_contract(c)

    def test_grouped_completion_refreshes_watchdog(self):
        with tempfile.TemporaryDirectory(dir=HERE) as d:
            p = pathlib.Path(d) / "stdout"
            p.write_text(json.dumps(row()) + "\n")
            guard = Guard(connections=1, t0=0, monitor_progress=False)
            reader = Progress(p)
            reader.poll(guard, 4)
            self.assertEqual(guard.completed, [6000])
            self.assertEqual(guard.last_progress, [4])
            with p.open("a") as f:
                f.write(json.dumps(row(2, 6000, 6000)) + "\n")
            reader.poll(guard, 5)
            self.assertEqual(guard.last_progress, [4])

    def test_invalid_grouped_progress_fails_closed(self):
        for key, value in [("errors", 1), ("evidence_valid", False), ("completed", 6001), ("sample_overflow_count", 1)]:
            with self.subTest(key=key), tempfile.TemporaryDirectory(dir=HERE) as d:
                r = row()
                r[key] = value
                p = pathlib.Path(d) / "stdout"
                p.write_text(json.dumps(r) + "\n")
                with self.assertRaises((ValueError, RuntimeError)):
                    Progress(p).poll(Guard(connections=1, t0=0), 1)

    def test_full_300s_paced_final(self):
        records = [row(i, i * 6000, (i - 1) * 6000) for i in range(1, 301)]
        counters = {
            k: records[-1][k] for k in ["offered", "reserved", "issued", "completed", "missed", "unreserved_current", "group_counters"]
        }
        final = dict(
            schema="nbsr-b5-grouped-final-v1",
            groups=1,
            payload_bytes=1024,
            streams_per_group=2,
            outstanding_per_stream=1,
            measurement_duration_ns=300_000_000_000,
            drain_duration_ns=0,
            **counters,
            max_outstanding_observed=2,
            errors=0,
            timeouts=0,
            collector_overflow_count=0,
            all_groups_joined=True,
            evidence_valid=True,
            source_cleanup={},
        )
        with tempfile.TemporaryDirectory(dir=HERE) as d:
            p = pathlib.Path(d) / "stdout"
            p.write_text("\n".join(map(json.dumps, records + [final])) + "\n")
            result = read_paced(p, cell())
            self.assertEqual(result["completed_operations"], 1800000)
            self.assertEqual(result["measured_ns"], 300_000_000_000)
            p.write_text("\n".join(map(json.dumps, records)) + "\n")
            with self.assertRaises(ValueError):
                read_paced(p, cell())


if __name__ == "__main__":
    unittest.main()
