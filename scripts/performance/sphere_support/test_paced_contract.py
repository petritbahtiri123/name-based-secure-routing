import unittest
import paced_contract as b


class BenchmarkContractTests(unittest.TestCase):
    def test_duration(self):
        self.assertEqual(b.duration(300), 300)
        for x in [60, 301, True, 300.0, None]:
            with self.assertRaises(ValueError):
                b.duration(x)

    def test_original_clocks(self):
        d = b.Deadline(100, 300)
        self.assertEqual(d.remaining("collection", 460), 10)
        with self.assertRaises(TimeoutError):
            d.remaining("work", 430)

    def test_full_measurement_gate(self):
        d = b.Deadline(0, 300)
        d.can_measure(27)
        with self.assertRaises(TimeoutError):
            d.can_measure(28)

    def test_tls(self):
        b.tls_remaining(450)
        b.tls_remaining(420, endpoint=True)
        with self.assertRaises(ValueError):
            b.tls_remaining(449)
        with self.assertRaises(ValueError):
            b.tls_remaining(419, endpoint=True)

    def sample(self, g, now, **kw):
        a = dict(
            now=now,
            memory=400 * b.MIB,
            tasks=40,
            available=3 * 1024**3,
            disk_free=3 * 1024**3,
            task_bytes=100 * b.MIB,
            tx=0,
            rx=0,
            drops=0,
            errors=0,
            oom=0,
            pids_denied=0,
            route="eth1",
        )
        a.update(kw)
        g.sample(**a)

    def test_memory_continuity(self):
        g = b.Guard(connections=1, t0=0)
        for t in range(5):
            self.sample(g, t, memory=461 * b.MIB)
        with self.assertRaises(RuntimeError):
            self.sample(g, 5, memory=461 * b.MIB)

    def test_memory_recovery(self):
        g = b.Guard(connections=1, t0=0)
        for t in range(4):
            self.sample(g, t, memory=461 * b.MIB)
        self.sample(g, 4)
        self.sample(g, 5, memory=461 * b.MIB)

    def test_two_network_samples(self):
        g = b.Guard(connections=1, t0=0)
        self.sample(g, 0)
        self.sample(g, 1, tx=13_000_000)
        with self.assertRaises(RuntimeError):
            self.sample(g, 2, tx=26_000_000)

    def test_progress_each_pair(self):
        g = b.Guard(connections=2, t0=0)
        g.progress(0, 1, 9)
        with self.assertRaises(RuntimeError):
            self.sample(g, 10)

    def test_resource_stops(self):
        for change in [
            dict(tasks=113),
            dict(oom=1),
            dict(pids_denied=1),
            dict(route="eth0"),
            dict(available=1),
            dict(task_bytes=257 * b.MIB),
        ]:
            with self.subTest(change=change), self.assertRaises(RuntimeError):
                self.sample(b.Guard(connections=1, t0=0), 1, **change)

    def test_gap_stops(self):
        g = b.Guard(connections=1, t0=0)
        self.sample(g, 0)
        with self.assertRaises(RuntimeError):
            self.sample(g, 3)


if __name__ == "__main__":
    unittest.main()
