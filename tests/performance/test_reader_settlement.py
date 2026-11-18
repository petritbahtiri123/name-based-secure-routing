import unittest
from scripts.performance import reader_settlement as candidate


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


class Owner:
    def __init__(self):
        self.identity = "owner-1"
        self.owned = True
        self.drain_failure = None
        self.cancelled = False
        self.killed = False
        self.code = 0
        self.live = False
        self.reaps = 0

    def observe(self):
        return self.code, self.live

    def reap(self):
        self.reaps += 1
        self.owned = False


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.owner = Owner()
        self.life = candidate.Lifecycle(
            run="next-run",
            source="source/stdout",
            owner="owner-1",
            anchor=0.0,
            deadline=150.0,
            caps={"capture": 16, "receipts": 16},
            clock=self.clock,
        )
        self.capture = lambda: dict(
            run="next-run", source="source/stdout", owner="owner-1", quiescent=True, final_valid=True, sha256="a" * 64
        )

    def close(self):
        self.life.checkpoint(self.owner, self.capture)

    def post(self):
        permit = self.life.begin_post()
        self.assertEqual(permit["operation"], "clock-probes-only")
        self.life.finish_post(permit, span_ns=20_000_000_000, probes_valid=True)

    def test_closes_inside_scan_before_slow_scan_finishes(self):
        self.clock.now = 70.0
        self.close()
        self.assertEqual(self.owner.reaps, 1)
        self.assertEqual(self.life.state, "CLOSED_UNSETTLED")
        self.post()
        self.clock.now += 24.0
        self.life.finish_settlement(valid=True, receipt_sha256="b" * 64)
        self.assertEqual(self.life.accept()["schema"], "nbsr-reader-lifecycle-v1")
        self.assertEqual(self.life.timings["closed"], 70.0)
        self.assertEqual(self.life.timings["settled"], 94.0)

    def test_live_descendant_never_releases(self):
        self.owner.live = True
        self.close()
        self.assertEqual(self.owner.reaps, 0)
        with self.assertRaises(ValueError):
            self.life.begin_post()

    def test_nonzero_exit_invalid(self):
        self.owner.code = 1
        with self.assertRaises(ValueError):
            self.close()
        self.assertEqual(self.life.state, "INVALID")

    def test_failed_drain_invalid(self):
        self.owner.drain_failure = "failed"
        with self.assertRaises(ValueError):
            self.close()

    def test_unquiescent_capture_invalid(self):
        self.capture = lambda: dict(
            run="next-run", source="source/stdout", owner="owner-1", quiescent=False, final_valid=True, sha256="a" * 64
        )
        with self.assertRaises(ValueError):
            self.close()

    def test_stale_identity_invalid(self):
        self.owner.identity = "stale"
        with self.assertRaises(ValueError):
            self.close()

    def test_reservations_apply_while_unsettled(self):
        self.close()
        out = []
        self.life.write("receipts", b"x" * 16, lambda b: out.append(b) or len(b))
        with self.assertRaises(ValueError):
            self.life.write("receipts", b"x", lambda b: len(b))
        self.assertEqual(len(out), 1)
        self.assertEqual(self.life.state, "INVALID")

    def test_short_write_invalidates_and_consumes_reservation(self):
        with self.assertRaises(ValueError):
            self.life.write("receipts", b"abc", lambda b: 2)
        self.assertEqual(self.life.used["receipts"], 3)
        self.assertEqual(self.life.state, "INVALID")

    def test_missing_settlement_prevents_accept(self):
        self.close()
        self.post()
        with self.assertRaises(ValueError):
            self.life.accept()

    def test_settlement_failure_still_fatal_after_post(self):
        self.close()
        self.post()
        with self.assertRaises(ValueError):
            self.life.finish_settlement(valid=False, receipt_sha256="b" * 64)
        self.assertEqual(self.life.state, "INVALID")

    def test_actual_span_still_rejected(self):
        self.close()
        permit = self.life.begin_post()
        with self.assertRaises(ValueError):
            self.life.finish_post(permit, span_ns=107488456282, probes_valid=True)

    def test_ninety_seconds_inclusive(self):
        self.close()
        permit = self.life.begin_post()
        self.life.finish_post(permit, span_ns=90000000000, probes_valid=True)

    def test_post_permit_one_use(self):
        self.close()
        self.post()
        with self.assertRaises(ValueError):
            self.life.begin_post()

    def test_deadline_not_renewed(self):
        self.clock.now = 150.0
        with self.assertRaises(TimeoutError):
            self.close()
        self.assertEqual(self.life.state, "INVALID")

    def test_cancelled_owner_never_releases(self):
        self.owner.cancelled = True
        with self.assertRaises(ValueError):
            self.close()

    def test_reap_must_close_handles(self):
        self.owner.reap = lambda: None
        with self.assertRaises(ValueError):
            self.close()

    def test_post_permit_binding(self):
        self.close()
        p = self.life.begin_post()
        p = dict(p, run="other")
        with self.assertRaises(ValueError):
            self.life.finish_post(p, span_ns=1, probes_valid=True)

    def test_clock_rollback_invalid(self):
        self.clock.now = 10.0
        self.close()
        self.clock.now = 9.0
        with self.assertRaises(ValueError):
            self.life.begin_post()


class ReconciliationTests(unittest.TestCase):
    setUp = LifecycleTests.setUp
    close = LifecycleTests.close
    post = LifecycleTests.post

    def test_slow_scanning_reaps_at_checkpoint_then_continues_full_scan(self):
        order = []
        self.owner.code = None

        def scan(tick):
            self.owner.code = 0
            self.clock.now = 70.0
            tick()
            order.append("scan-tail")
            self.clock.now = 94.0
            tick()
            return dict(valid=True, receipt_sha256="b" * 64)

        def post(permit):
            order.append("post")
            self.assertEqual(self.owner.reaps, 1)
            self.assertEqual(self.life.state, "CLOSED_UNSETTLED")
            return dict(span_ns=20_000_000_000, probes_valid=True)

        self.assertTrue(hasattr(self.life, "reconcile"), "checkpoint-driven reconciliation missing")
        self.life.reconcile(scan, self.owner, self.capture, post)
        self.assertEqual(order, ["post", "scan-tail"])
        self.assertEqual(self.life.timings["closed"], 70.0)
        self.assertEqual(self.life.timings["post_finished"], 70.0)
        self.assertEqual(self.life.timings["settled"], 94.0)
        self.assertTrue(self.life.accept()["lifecycle_complete"])

    def test_late_scan_failure_invalidates_successful_post(self):
        def scan(tick):
            tick()
            raise OSError("read failure")

        self.assertTrue(hasattr(self.life, "reconcile"), "checkpoint-driven reconciliation missing")
        with self.assertRaises(OSError):
            self.life.reconcile(scan, self.owner, self.capture, lambda p: dict(span_ns=1, probes_valid=True))
        self.assertEqual(self.life.state, "INVALID")

    def test_numeric_truth_is_not_capture_proof(self):
        self.capture = lambda: dict(run="next-run", source="source/stdout", owner="owner-1", quiescent=1, final_valid=True, sha256="a" * 64)
        with self.assertRaises(ValueError):
            self.close()

    def test_missing_scan_receipt_invalidates(self):
        with self.assertRaises(ValueError):
            self.life.reconcile(lambda tick: None, self.owner, self.capture, lambda p: dict(span_ns=1, probes_valid=True))
        self.assertEqual(self.life.state, "INVALID")

    def test_scan_timeout_after_successful_post_invalidates(self):
        def scan(tick):
            self.clock.now = 150.0
            return dict(valid=True, receipt_sha256="b" * 64)

        with self.assertRaises(TimeoutError):
            self.life.reconcile(scan, self.owner, self.capture, lambda p: dict(span_ns=1, probes_valid=True))

    def test_overflow_during_scan_invalidates(self):
        def scan(tick):
            self.life.write("capture", b"x" * 17, lambda b: len(b))
            return dict(valid=True, receipt_sha256="b" * 64)

        with self.assertRaises(ValueError):
            self.life.reconcile(scan, self.owner, self.capture, lambda p: dict(span_ns=1, probes_valid=True))

    def test_untrusted_probe_success_false_invalidates(self):
        with self.assertRaises(ValueError):
            self.life.reconcile(
                lambda tick: dict(valid=True, receipt_sha256="b" * 64),
                self.owner,
                self.capture,
                lambda p: dict(span_ns=1, probes_valid=False),
            )

    def test_scan_must_finish_before_acceptance(self):
        def scan(tick):
            self.assertFalse(self.life._settled)
            return dict(valid=True, receipt_sha256="b" * 64)

        self.life.reconcile(scan, self.owner, self.capture, lambda p: dict(span_ns=1, probes_valid=True))
        self.assertEqual(self.life.accept()["campaign_validity"], "REQUIRES_OTHER_GATES")

    def test_cancel_after_closure_invalidates_without_checkpoint(self):
        self.close()
        self.post()
        self.life.finish_settlement(valid=True, receipt_sha256="b" * 64)
        self.owner.cancelled = True
        with self.assertRaises(ValueError):
            self.life.accept()

    def test_capture_frozen_after_final_hash(self):
        self.close()
        written = []
        with self.assertRaises(ValueError):
            self.life.write("capture", b"x", lambda b: written.append(b) or len(b))
        self.assertEqual(written, [])

    def test_all_writes_frozen_after_settlement(self):
        self.close()
        self.post()
        self.life.finish_settlement(valid=True, receipt_sha256="b" * 64)
        written = []
        with self.assertRaises(ValueError):
            self.life.write("receipts", b"x", lambda b: written.append(b) or len(b))
        self.assertEqual(written, [])


if __name__ == "__main__":
    unittest.main()
