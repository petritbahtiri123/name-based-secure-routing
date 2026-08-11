import unittest
from pathlib import Path
import tempfile

from scripts.performance.p2a_established import build_matrix, coefficient_of_variation, validate_repeat
from scripts.run_p2a_established import clear_cell_artifacts, clear_run_markers, summarize_resources


class P2AEstablishedTests(unittest.TestCase):
    def test_matrix_is_exactly_eighteen_matched_cells(self):
        cells = build_matrix()
        self.assertEqual(len(cells), 18)
        self.assertEqual({c["path"] for c in cells}, {"direct", "nbsr"})
        self.assertEqual({c["streams"] for c in cells}, {1, 8, 64})
        self.assertEqual({c["payload_bytes"] for c in cells}, {1, 1024, 16384})

    def test_cv_uses_sample_standard_deviation(self):
        self.assertAlmostEqual(coefficient_of_variation([95.0, 100.0, 105.0]), 0.05)

    def test_repeat_rejects_any_timed_lifecycle_or_replay_growth(self):
        base = {
            "completed_operations": 10,
            "errors": 0,
            "missing": 0,
            "duplicates": 0,
            "corrupt": 0,
            "wrong_request": 0,
            "transport_sessions_created_delta": 0,
            "service_channels_created_delta": 0,
            "application_streams_created_delta": 0,
            "replay_entries_delta": 0,
        }
        self.assertTrue(validate_repeat(base))
        for key in (
            "transport_sessions_created_delta",
            "service_channels_created_delta",
            "application_streams_created_delta",
            "replay_entries_delta",
        ):
            changed = dict(base)
            changed[key] = 1
            self.assertFalse(validate_repeat(changed), key)

    def test_repeat_rejects_silent_failures(self):
        record = {
            "completed_operations": 1,
            "errors": 0,
            "missing": 0,
            "duplicates": 0,
            "corrupt": 0,
            "wrong_request": 1,
            "transport_sessions_created_delta": 0,
            "service_channels_created_delta": 0,
            "application_streams_created_delta": 0,
            "replay_entries_delta": 0,
        }
        self.assertFalse(validate_repeat(record))

    def test_stale_run_markers_are_removed_before_peer_launch(self):
        with tempfile.TemporaryDirectory() as temporary:
            paths = [Path(temporary) / name for name in ("ready", "result", "ack")]
            for path in paths:
                path.write_text("stale", encoding="utf-8")
            clear_run_markers(*paths)
            self.assertEqual([path.exists() for path in paths], [False, False, False])

    def test_resource_summary_excludes_setup_and_warmup_samples(self):
        samples = [
            {"role": "source", "timestamp_ns": 0, "user_cpu_ns": 0, "kernel_cpu_ns": 0,
             "peak_working_set_bytes": 999, "private_bytes": 999},
            {"role": "source", "timestamp_ns": 10_000_000_000, "user_cpu_ns": 100, "kernel_cpu_ns": 50,
             "peak_working_set_bytes": 100, "private_bytes": 80},
            {"role": "source", "timestamp_ns": 40_000_000_000, "user_cpu_ns": 400, "kernel_cpu_ns": 200,
             "peak_working_set_bytes": 120, "private_bytes": 90},
        ]
        result = summarize_resources(samples, completed=10, measured_seconds=30)
        self.assertEqual(result["total_cpu_ns"], 450)
        self.assertEqual(result["roles"]["source"]["peak_working_set_bytes"], 120)

    def test_cell_cleanup_removes_only_matching_prior_repeat_artifacts(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            matching = root / "nbsr-s64-p1-r5.json"
            sibling = root / "direct-s64-p1-r5.json"
            matching.write_text("stale", encoding="utf-8")
            sibling.write_text("keep", encoding="utf-8")
            clear_cell_artifacts(root, "nbsr", 64, 1)
            self.assertFalse(matching.exists())
            self.assertTrue(sibling.exists())


if __name__ == "__main__":
    unittest.main()
