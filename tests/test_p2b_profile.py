import unittest
import tempfile
from pathlib import Path

from scripts.performance.p2b_profile import (
    LOADS,
    observer_effect,
    profile_manifest,
    shard_plan,
)


class P2BProfileTests(unittest.TestCase):
    def test_runner_removes_stale_per_run_markers(self):
        from scripts.run_p2b_profile import reset_markers

        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / "ready.json"
            marker.write_text("stale", encoding="utf-8")
            reset_markers(marker)
            self.assertFalse(marker.exists())

    def test_loads_reuse_exact_accepted_capacity_percentages(self):
        self.assertEqual(LOADS["direct"][50], 2375.0)
        self.assertEqual(LOADS["direct"][90], 4275.0)
        self.assertEqual(LOADS["nbsr"][50], 843.75)
        self.assertEqual(LOADS["nbsr"][90], 1518.75)

    def test_shards_never_reach_p1f_cap_and_preserve_total(self):
        shards = shard_plan(1518.75, 180)
        self.assertEqual(sum(shards), round(1518.75 * 180))
        self.assertTrue(shards)
        self.assertLessEqual(max(shards), 8000)
        self.assertGreater(min(shards), 0)

    def test_manifest_freezes_matched_lifecycle_model(self):
        direct = profile_manifest("direct", 50, 1, 180, False)
        nbsr = profile_manifest("nbsr", 50, 1, 180, True)
        for manifest in (direct, nbsr):
            self.assertEqual(manifest["payload_bytes"], 1024)
            self.assertEqual(manifest["operation"], "new-application-stream-lifecycle")
            self.assertEqual(manifest["connection_model"], "persistent-per-shard")
            self.assertEqual(manifest["max_operations_per_session"], 8000)
        self.assertFalse(direct["instrumentation_enabled"])
        self.assertTrue(nbsr["instrumentation_enabled"])

    def test_observer_effect_applies_exact_median_guardrails(self):
        passed = observer_effect(
            disabled_throughput=[100.0, 100.0, 100.0],
            enabled_throughput=[97.0, 98.0, 97.0],
            disabled_p99=[1000, 1000, 1000],
            enabled_p99=[1050, 1040, 1050],
            disabled_errors=0,
            enabled_errors=0,
        )
        self.assertTrue(passed["passed"])
        failed = observer_effect(
            disabled_throughput=[100.0] * 3,
            enabled_throughput=[96.0] * 3,
            disabled_p99=[1000] * 3,
            enabled_p99=[1000] * 3,
            disabled_errors=0,
            enabled_errors=0,
        )
        self.assertFalse(failed["passed"])


if __name__ == "__main__":
    unittest.main()
