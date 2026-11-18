"""No native processes: exact binding contract around an injected native owner."""

import unittest
from scripts.performance import reader_settlement as candidate


class Native:
    def __init__(self):
        self.argv = ("python", "reader")
        self.deadline = 150.0
        self.started = True
        self.assigned = True
        self.job = object()
        self.process = object()
        self.thread = object()
        self.cancelled = False
        self.killed = False
        self.drain_failure = None
        self.code = 0
        self.live = False

    @property
    def owned(self):
        return any(x is not None for x in (self.job, self.process, self.thread))

    def observe(self):
        return self.code, self.live

    def reap(self):
        if self.code != 0 or self.live:
            raise RuntimeError("not empty")
        self.job = self.process = self.thread = None


class BindingTests(unittest.TestCase):
    def bind(self, n):
        self.assertTrue(hasattr(candidate, "BoundReaderOwner"), "native owner binding missing")
        return candidate.BoundReaderOwner(n, run="r", source="stdout", request_sha256="a" * 64, argv=("python", "reader"), deadline=150.0)

    def test_consumes_exact_owner_once(self):
        n = Native()
        b = self.bind(n)
        identity = b.identity
        self.assertEqual(b.observe(), (0, False))
        b.reap()
        self.assertFalse(b.owned)
        self.assertEqual(b.identity, identity)
        with self.assertRaises(ValueError):
            b.reap()

    def test_wrong_argv_rejected(self):
        n = Native()
        n.argv = ("other",)
        with self.assertRaises(ValueError):
            self.bind(n)

    def test_handle_replacement_rejected(self):
        n = Native()
        b = self.bind(n)
        n.job = object()
        with self.assertRaises(ValueError):
            b.observe()

    def test_deadline_change_rejected(self):
        n = Native()
        b = self.bind(n)
        n.deadline = 151.0
        with self.assertRaises(ValueError):
            b.observe()

    def test_reap_without_empty_observation_rejected(self):
        b = self.bind(Native())
        with self.assertRaises(ValueError):
            b.reap()

    def test_identity_bound_to_run_and_source(self):
        n = Native()
        b = self.bind(n)
        c = candidate.BoundReaderOwner(
            Native(), run="other", source="stdout", request_sha256="a" * 64, argv=("python", "reader"), deadline=150.0
        )
        self.assertNotEqual(b.identity, c.identity)

    def lifecycle(self, bound):
        life = candidate.Lifecycle(
            run="r",
            source="stdout",
            owner=bound.identity,
            anchor=0.0,
            deadline=150.0,
            caps={"capture": 16, "receipts": 16},
            clock=lambda: 1.0,
        )
        def proof():
            return dict(run="r", source="stdout", owner=life.identity["owner"], quiescent=True, final_valid=True, sha256="b" * 64)
        life.checkpoint(bound, proof)
        return life

    def test_deadline_drift_restore_cannot_recover_lifecycle(self):
        n = Native()
        b = self.bind(n)
        life = self.lifecycle(b)
        n.deadline = 151.0
        with self.assertRaises(ValueError):
            life.begin_post()
        n.deadline = 150.0
        self.assertEqual(life.state, "INVALID")
        with self.assertRaises(ValueError):
            life.begin_post()

    def test_handle_return_restore_cannot_recover_lifecycle(self):
        n = Native()
        b = self.bind(n)
        life = self.lifecycle(b)
        n.job = object()
        with self.assertRaises(ValueError):
            life.begin_post()
        n.job = None
        self.assertEqual(life.state, "INVALID")
        with self.assertRaises(ValueError):
            life.begin_post()

    def test_binding_verification_failure_latches_even_outside_lifecycle(self):
        n = Native()
        b = self.bind(n)
        n.deadline = 151.0
        with self.assertRaises(ValueError):
            b.observe()
        n.deadline = 150.0
        with self.assertRaises(ValueError):
            b.observe()
