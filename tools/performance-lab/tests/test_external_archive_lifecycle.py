"""Synthetic archive lifecycle: never remove the Lab's operational raw store."""

import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from fastapi.testclient import TestClient
from lab.app import create_app


class ExternalArchiveLifecycle(unittest.TestCase):
    def test_campaign_copy_removal_keeps_dashboard_and_exact_download(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            campaign = root / "campaign"
            campaign.mkdir()
            source = campaign / "evidence.json"
            raw = json.dumps(
                {
                    "schema": "nbsr-sphere-controlled-load-summary-v1",
                    "date": "2026-10-19",
                    "shape": {
                        "aggregate_offered_operations_per_second": 8000,
                        "request_bytes": 1024,
                        "response_bytes": 1024,
                    },
                    "measurement": {
                        "measurement_seconds": 300,
                        "offered_operations": 2400000,
                        "completed_operations": 2397718,
                        "missed_offer_slots": 2282,
                        "errors": 0,
                        "timeouts": 0,
                        "median_window_quantiles_us": {"p99": 212.049},
                        "capacity": "NOT_ESTABLISHED",
                    },
                }
            ).encode()
            source.write_bytes(raw)
            with TestClient(create_app(root / "lab")) as client:
                response = client.post(
                    "/api/v1/ingestions",
                    content=raw,
                    headers={"content-type": "application/json"},
                )
                self.assertEqual(response.status_code, 200)
                sha = response.json()["sha256"]
                self.assertEqual(sha, hashlib.sha256(raw).hexdigest())
                before = client.get("/api/v1/runs").json()
                self.assertEqual(len(before["runs"]), 1)
                archive = campaign / "evidence.zip"
                with zipfile.ZipFile(archive, "x", zipfile.ZIP_DEFLATED) as z:
                    z.write(source, "evidence.json")
                restore = root / "restore"
                restore.mkdir()
                with zipfile.ZipFile(archive) as z:
                    (restore / "evidence.json").write_bytes(z.read("evidence.json"))
                self.assertEqual((restore / "evidence.json").read_bytes(), raw)
                self.assertEqual(client.get("/api/v1/artifacts/" + sha).content, raw)
                source.unlink()  # Only this freshly created test fixture.
                self.assertEqual(client.get("/api/v1/runs").json(), before)
                download = client.get("/api/v1/artifacts/" + sha)
                self.assertEqual(download.status_code, 200)
                self.assertEqual(download.content, raw)
                self.assertEqual(hashlib.sha256(download.content).hexdigest(), sha)
                self.assertTrue((root / "lab/metadata.sqlite3").exists())
                self.assertTrue((root / "lab/sha256" / sha[:2] / sha).exists())

    def test_missing_operational_raw_is_not_recovered_from_campaign_zip(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw = b'{"schema":"unknown-fixture"}'
            with TestClient(create_app(root / "lab")) as client:
                sha = client.post(
                    "/api/v1/ingestions",
                    content=raw,
                    headers={"content-type": "application/json"},
                ).json()["sha256"]
                with zipfile.ZipFile(root / "evidence.zip", "x") as z:
                    z.writestr("evidence.json", raw)
                (
                    root / "lab/sha256" / sha[:2] / sha
                ).unlink()  # Test-only failure case.
                self.assertEqual(
                    client.get("/api/v1/artifacts/" + sha).status_code, 404
                )


if __name__ == "__main__":
    unittest.main()
