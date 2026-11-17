import hashlib
import json
import tempfile
import unittest
from pathlib import Path
import importlib.util

spec = importlib.util.spec_from_file_location("weekly_adapter", Path(__file__).resolve().parents[2] / "scripts/ci/build_weekly_api_plan.py")
a = importlib.util.module_from_spec(spec)
spec.loader.exec_module(a)


class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.addCleanup(self.t.cleanup)
        self.root = Path(self.t.name)
        self.src = self.root / "snapshot"
        self.src.mkdir()
        (self.src / "sources").mkdir()
        self.out = self.root / "run"
        self.data = b"print(1)\n"
        self.blob = hashlib.sha1(b"blob 9\0" + self.data).hexdigest()
        (self.src / "sources" / self.blob).write_bytes(self.data)
        self.f = {
            "path": "a.py",
            "git_blob": self.blob,
            "sha256": a.sha(self.data),
            "bytes": len(self.data),
            "status": "planned",
            "chunks": [{"start_byte": 0, "end_byte": 9, "bytes": 9, "sha256": a.sha(self.data)}],
        }
        self.doc = {
            "repository": a.REPOSITORY,
            "ref": a.REF,
            "scope": a.SCOPE,
            "commit": "a" * 40,
            "preparation_complete": True,
            "files": [self.f],
        }
        self.save()

    def save(self):
        self.doc["source_set_sha256"] = a.source_set(self.doc["files"])
        (self.src / "snapshot.json").write_text(json.dumps(self.doc))

    def test_prepare(self):
        r = a.prepare(self.src, self.out)
        self.assertEqual(r["candidate_bytes"], 9)
        self.assertEqual(r["weekly_limit_usd"], "10.00")
        self.assertTrue((self.out / "plan.json").exists())

    def test_incomplete(self):
        self.doc["preparation_complete"] = False
        self.save()
        with self.assertRaises(ValueError):
            a.prepare(self.src, self.out)

    def test_wrong_ref(self):
        self.doc["ref"] = "refs/heads/main"
        self.save()
        with self.assertRaises(ValueError):
            a.prepare(self.src, self.out)

    def test_changed_source(self):
        (self.src / "sources" / self.blob).write_bytes(b"changed")
        with self.assertRaises(ValueError):
            a.prepare(self.src, self.out)

    def test_chunk_gap(self):
        self.f["chunks"][0]["start_byte"] = 1
        self.save()
        with self.assertRaises(ValueError):
            a.prepare(self.src, self.out)

    def test_preserves_exclusion(self):
        self.doc["files"].append({"path": "z.bin", "status": "excluded", "reason": "binary"})
        self.save()
        self.assertEqual(a.prepare(self.src, self.out)["excluded"][0]["path"], "z.bin")

    def test_no_overwrite(self):
        a.prepare(self.src, self.out)
        with self.assertRaises(FileExistsError):
            a.prepare(self.src, self.out)

    def test_linked_source(self):
        # Path traversal is rejected before any read.
        self.f["git_blob"] = "../outside"
        self.save()
        with self.assertRaises(ValueError):
            a.prepare(self.src, self.out)

    def test_empty_planned_set(self):
        self.doc["files"] = [{"path": "z.bin", "status": "excluded", "reason": "binary"}]
        self.save()
        with self.assertRaises(ValueError):
            a.prepare(self.src, self.out)

    def test_exact_range_coverage(self):
        plan = a.prepare(self.src, self.out)
        ranges = [r for item in plan["requests"] for r in item["ranges"]]
        self.assertEqual(sum(r["byte_end"] - r["byte_start"] for r in ranges), len(self.data))
        self.assertEqual([(r["path"], r["byte_start"], r["byte_end"]) for r in ranges], [("a.py", 0, 9)])

    def test_long_utf8_line_exact_segments(self):
        for number, data in enumerate([b"x" * 145000, ("é😀" * 30000).encode(), b"prefix\n" + b"x" * 512000 + b"\ntail\n"]):
            with self.subTest(number=number):
                blob = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
                (self.src / "sources" / blob).write_bytes(data)
                self.f.update(
                    git_blob=blob,
                    sha256=a.sha(data),
                    bytes=len(data),
                    chunks=[{"start_byte": 0, "end_byte": len(data), "bytes": len(data), "sha256": a.sha(data)}],
                )
                self.save()
                out = self.root / ("long" + str(number))
                plan = a.prepare(self.src, out)
                end = 0
                for item in plan["requests"]:
                    payload_bytes = (out / "requests" / (item["request_sha256"] + ".json")).read_bytes()
                    self.assertLessEqual(len(payload_bytes), 96000)
                    payload = json.loads(payload_bytes)
                    for r in item["ranges"]:
                        lo, hi = r["byte_start"], r["byte_end"]
                        self.assertEqual(lo, end)
                        end = hi
                        part = data[lo:hi].decode()
                        first = data[:lo].count(b"\n") + 1
                        self.assertEqual(r["line_start"], first)
                        expected = "".join(f"{n}: {line}" for n, line in enumerate(part.splitlines(keepends=True), first))
                        self.assertIn(expected, payload["input"])
                self.assertEqual(end, len(data))


if __name__ == "__main__":
    unittest.main()
