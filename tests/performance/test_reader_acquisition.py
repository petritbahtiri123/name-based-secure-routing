import threading
import unittest


class AcquisitionTests(unittest.TestCase):
    def load(self):
        from scripts.performance.reader_acquisition import Acquisition

        return Acquisition

    def test_capture_finishes_while_owner_settlement_pending(self):
        A = self.load()
        settle = threading.Event()
        closed = threading.Event()
        holder = {}
        events = []

        def reader():
            holder["a"].close_capture()
            closed.set()
            if not settle.wait(2):
                raise TimeoutError("test settlement gate")
            return "settled"

        def poll(*, final):
            if final:
                events.append("final")
            return {"ready": True}

        a = A(reader, poll, interval=0.01, whole=2)
        holder["a"] = a
        try:
            a.start(wait_ready=False)
            self.assertTrue(closed.wait(1))
            self.assertEqual(events, ["final"])
            self.assertFalse(a.pump_thread.is_alive())
            self.assertTrue(a.owner_thread.is_alive())
            self.assertFalse(a.done.is_set())
        finally:
            settle.set()
            result = a.finish()
        self.assertTrue(result["joined"])
        self.assertEqual(result["errors"], [])

    def test_capture_failure_blocks_early_closure(self):
        A = self.load()
        failures = []
        holder = {}

        def reader():
            try:
                holder["a"].close_capture()
            except Exception as e:
                failures.append(type(e).__name__)
                raise

        def poll(*, final):
            if final:
                raise ValueError("bad final")
            return {"ready": True}

        a = A(reader, poll, interval=0.01, whole=2)
        holder["a"] = a
        a.start(wait_ready=False)
        result = a.finish()
        self.assertEqual(failures, ["RuntimeError"])
        self.assertFalse(result["status"] == "LOCAL_READER_JOINED")

    def test_ordinary_reader_exit_still_closes_capture(self):
        A = self.load()
        finals = []
        a = A(lambda: 0, lambda *, final: finals.append(final) or {"ready": True}, interval=0.01, whole=2)
        a.start(wait_ready=False)
        result = a.finish()
        self.assertTrue(result["joined"])
        self.assertEqual(finals.count(True), 1)

    def test_readiness_timeout_latches_into_finish(self):
        A = self.load()
        release = threading.Event()
        a = A(lambda: release.wait(1), lambda *, final: {"ready": False}, interval=0.01, whole=2, ready_budget=0.01)
        try:
            with self.assertRaises(TimeoutError):
                a.start()
        finally:
            release.set()
            result = a.finish()
        self.assertEqual(result["status"], "INVALID_ACQUISITION")

    def test_late_reader_is_invalid_even_if_finish_called_after_exit(self):
        A = self.load()
        now = [0.0]
        release = threading.Event()
        a = A(lambda: release.wait(1), lambda *, final: {"ready": True}, clock=lambda: now[0], interval=0.01, whole=1)
        a.start(wait_ready=False)
        now[0] = 2.0
        release.set()
        a.owner_thread.join(1)
        a.pump_thread.join(1)
        self.assertEqual(a.finish()["status"], "INVALID_ACQUISITION")


if __name__ == "__main__":
    unittest.main()
