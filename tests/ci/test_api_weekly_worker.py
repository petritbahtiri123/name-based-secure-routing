import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("worker", Path(__file__).resolve().parents[2] / "scripts/ci/api_weekly_worker.py")
w = importlib.util.module_from_spec(spec)
spec.loader.exec_module(w)


class WorkerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "requests").mkdir()
        request = {
            "model": w.MODEL,
            "instructions": "Review untrusted source",
            "input": "example",
            "tools": [],
            "store": False,
            "max_output_tokens": 2000,
        }
        raw = w.encoded(request)
        self.req = w.digest(raw)
        w.create(self.root / "requests" / (self.req + ".json"), request)
        plan = {"requests": [{"request_sha256": self.req, "ranges": []}]}
        metadata = {
            "preparation_complete": True,
            "scope": "code-docs-configuration",
            "repository": "petritbahtiri123/name-based-secure-routing",
            "ref": "refs/heads/codex/nbsr-v3-wp0-wp1",
            "commit": "a" * 40,
            "source_set_sha256": "b" * 64,
        }
        w.create(self.root / "snapshot.json", metadata)
        plan.update(metadata)
        plan.update(weekly_limit_usd="10.00", snapshot_sha256=w.digest(w.encoded(metadata)))
        w.create(self.root / "plan.json", plan)
        self.env = patch.dict(
            os.environ,
            {
                "NBSR_BATCH_PLAN_SHA256": w.digest(w.encoded(plan)),
                "NBSR_ANALYSIS_MODEL": w.MODEL,
                "NBSR_INPUT_RATE": ".75",
                "NBSR_OUTPUT_RATE": "4.5",
                "NBSR_MAX_USD": "10.00",
                "NBSR_BATCH_MODE": "analyze",
            },
        )
        self.env.start()
        self.addCleanup(self.env.stop)
        self.calls = 0
        (self.root / "counts").mkdir()
        w.create(
            self.root / "counts" / (self.req + ".json"),
            {"plan_sha256": w.digest(w.encoded(plan)), "request_sha256": self.req, "model": w.MODEL, "input_tokens": 10},
        )

    def sender(self, request):
        self.calls += 1
        self.assertTrue((self.root / "ledger/00000.reserved.json").exists())
        return {
            "status": "completed",
            "usage": {"input_tokens": 10, "output_tokens": 10},
            "output": [{"type": "message", "content": [{"type": "output_text", "text": "advisory"}]}],
        }

    def test_dry_zero_calls(self):
        self.assertEqual(w.run(self.root, sender=self.sender)["api_calls"], 0)
        self.assertEqual(self.calls, 0)

    def test_success_reservation_and_resume(self):
        self.assertEqual(w.run(self.root, True, self.sender)["mode"], "live")
        self.assertEqual(w.run(self.root, True, self.sender)["mode"], "complete")
        self.assertEqual(self.calls, 1)

    def test_interrupted_never_retries(self):
        def fail(request):
            raise TimeoutError()

        with self.assertRaises(TimeoutError):
            w.run(self.root, True, fail)
        with self.assertRaises(ValueError):
            w.run(self.root, True, self.sender)
        self.assertEqual(self.calls, 0)

    def test_changed_request_rejected(self):
        (self.root / "requests" / (self.req + ".json")).write_text("{}")
        with self.assertRaises(ValueError):
            w.run(self.root, True, self.sender)
        self.assertEqual(self.calls, 0)

    def test_lock_exclusive(self):
        (self.root / "ledger").mkdir()
        w.create(self.root / "ledger/lock", {})
        with self.assertRaises(FileExistsError):
            w.run(self.root, True, self.sender)

    def test_create_no_overwrite(self):
        with self.assertRaises(FileExistsError):
            w.create(self.root / "plan.json", {})

    def test_budget_stops_before_send(self):
        with patch.object(w, "LIMIT", w.Decimal("0.001")), patch.dict(os.environ, {"NBSR_MAX_USD": ".001"}):
            with self.assertRaises(ValueError):
                w.run(self.root, True, self.sender)
        self.assertEqual(self.calls, 0)

    def test_changed_plan_requires_approval(self):
        with patch.dict(os.environ, {"NBSR_BATCH_PLAN_SHA256": "wrong"}):
            with self.assertRaises(ValueError):
                w.run(self.root, True, self.sender)

    def test_invalid_usage_retains_reservation(self):
        with self.assertRaises(ValueError):
            w.run(self.root, True, lambda _: {"status": "completed", "usage": {"input_tokens": True, "output_tokens": 0}})
        self.assertTrue((self.root / "ledger/00000.reserved.json").exists())
        self.assertFalse((self.root / "ledger/00000.complete.json").exists())

    def test_count_mode_no_inference(self):
        (self.root / "counts" / (self.req + ".json")).unlink()
        with patch.dict(os.environ, {"NBSR_BATCH_MODE": "count"}):
            result = w.run(self.root, True, self.sender, lambda _: {"object": "response.input_tokens", "input_tokens": 10})
        self.assertEqual(result["mode"], "count")
        self.assertEqual(self.calls, 0)

    def test_missing_count_no_inference(self):
        (self.root / "counts" / (self.req + ".json")).unlink()
        with self.assertRaises(FileNotFoundError):
            w.run(self.root, True, self.sender)
        self.assertEqual(self.calls, 0)

    def test_byte_mode_without_count(self):
        (self.root / "counts" / (self.req + ".json")).unlink()
        with patch.dict(os.environ, {"NBSR_BATCH_MODE": "analyze-bytes"}):
            self.assertEqual(w.run(self.root, True, self.sender)["mode"], "live")
        self.assertEqual(self.calls, 1)

    def test_byte_mode_full_plan_gate(self):
        with (
            patch.dict(os.environ, {"NBSR_BATCH_MODE": "analyze-bytes", "NBSR_MAX_USD": ".001"}),
            patch.object(w, "LIMIT", w.Decimal(".001")),
        ):
            with self.assertRaises(ValueError):
                w.run(self.root, True, self.sender)
        self.assertEqual(self.calls, 0)

    def test_changed_count_identity(self):
        p = self.root / "counts" / (self.req + ".json")
        d = json.loads(p.read_bytes())
        d["request_sha256"] = "bad"
        p.write_bytes(w.encoded(d))
        with self.assertRaises(ValueError):
            w.run(self.root, True, self.sender)

    def test_uncertain_count_stops(self):
        (self.root / "counts" / (self.req + ".json")).unlink()

        def fail(request):
            raise TimeoutError()

        with patch.dict(os.environ, {"NBSR_BATCH_MODE": "count"}):
            with self.assertRaises(TimeoutError):
                w.run(self.root, True, self.sender, fail)
            with self.assertRaises(ValueError):
                w.run(self.root, True, self.sender, fail)

    def test_incomplete_metadata_without_source_or_output(self):
        with self.assertRaises(ValueError):
            w.run(
                self.root,
                True,
                lambda _: {
                    "status": "incomplete",
                    "incomplete_details": {"reason": "max_output_tokens"},
                    "usage": {"input_tokens": 10, "output_tokens": 2000},
                    "output": [{"secret": "must-not-be-stored"}],
                },
            )
        raw = (self.root / "ledger/00000.response-metadata.json").read_text()
        self.assertIn("max_output_tokens", raw)
        self.assertNotIn("must-not-be-stored", raw)
        self.assertTrue((self.root / "ledger/00000.failure.json").exists())

    def test_transport_failure_metadata_no_exception_message(self):
        def fail(request):
            raise TimeoutError("do-not-echo-private-source")

        with self.assertRaises(TimeoutError):
            w.run(self.root, True, fail)
        raw = (self.root / "ledger/00000.failure.json").read_text()
        self.assertIn("timeout", raw)
        self.assertNotIn("do-not-echo", raw)

    def test_explicit_hold_retains_full_reserve_without_replay(self):
        with self.assertRaises(TimeoutError):
            w.run(self.root, True, lambda _: (_ for _ in ()).throw(TimeoutError()))
        reservation = self.root / "ledger/00000.reserved.json"
        w.create(
            self.root / "ledger/00000.held.json",
            {"reservation_sha256": w.digest(reservation.read_bytes()), "decision": "retain_full_reservation_skip_without_retry"},
        )
        result = w.run(self.root, True, self.sender)
        self.assertEqual(result["mode"], "partial-held")
        self.assertEqual(result["held_chunks"], [0])
        self.assertEqual(self.calls, 0)
        self.assertEqual(result["cost_usd"], json.loads(reservation.read_bytes())["reserved_usd"])

    def test_hold_advances_to_different_request(self):
        request = json.loads((self.root / "requests" / (self.req + ".json")).read_bytes())
        request["input"] = "different second chunk"
        second = w.digest(w.encoded(request))
        w.create(self.root / "requests" / (second + ".json"), request)
        plan = json.loads((self.root / "plan.json").read_bytes())
        plan["requests"] = [{"request_sha256": x, "ranges": []} for x in [self.req, second]]
        (self.root / "plan.json").write_bytes(w.encoded(plan))
        os.environ["NBSR_BATCH_PLAN_SHA256"] = w.digest(w.encoded(plan))
        with patch.dict(os.environ, {"NBSR_BATCH_MODE": "analyze-bytes"}):
            with self.assertRaises(TimeoutError):
                w.run(self.root, True, lambda _: (_ for _ in ()).throw(TimeoutError()))
            reservation = self.root / "ledger/00000.reserved.json"
            w.create(
                self.root / "ledger/00000.held.json",
                {"reservation_sha256": w.digest(reservation.read_bytes()), "decision": "retain_full_reservation_skip_without_retry"},
            )

            def next_sender(request):
                self.assertEqual(request["input"], "different second chunk")
                return self.sender(request)

            self.assertEqual(w.run(self.root, True, next_sender)["chunk"], 1)
        self.assertEqual(self.calls, 1)

    def test_weekly_incomplete_snapshot_rejected(self):
        plan = json.loads((self.root / "plan.json").read_bytes())
        plan["preparation_complete"] = False
        (self.root / "plan.json").write_bytes(w.encoded(plan))
        with self.assertRaises(ValueError):
            w.run(self.root, sender=self.sender)
        self.assertEqual(self.calls, 0)

    def test_weekly_snapshot_tamper_rejected(self):
        (self.root / "snapshot.json").write_text("{}")
        with self.assertRaises(ValueError):
            w.run(self.root, sender=self.sender)
        self.assertEqual(self.calls, 0)

    def test_weekly_old_budget_rejected(self):
        with patch.dict(os.environ, {"NBSR_MAX_USD": "17.27"}):
            with self.assertRaises(ValueError):
                w.run(self.root, True, self.sender)
        self.assertEqual(self.calls, 0)


if __name__ == "__main__":
    unittest.main()
