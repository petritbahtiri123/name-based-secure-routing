import hashlib
import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("export_context", Path(__file__).with_name("export_context.py"))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ExportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.repo = self.base / "repo"
        self.repo.mkdir()
        self.names = set(module.REQUIRED)
        for name in self.names:
            path = self.repo / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"dirty current source")
        self.output = self.base / "export"
        self.patcher = patch.object(module, "git", side_effect=self.git)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def git(self, repo, *args):
        if args[0] == "rev-parse":
            return b"a" * 40
        return b"".join(b"100644 " + b"b" * 40 + b" 0\t" + n.encode() + b"\0" for n in sorted(self.names))

    def test_exact_dirty_snapshot_and_no_untracked_or_credentials(self):
        for name in ("tools/demo-lab/private-user.json", "tools/demo-lab/secret.pem",
                     "tools/demo-lab/runtime/leaked.json", "unrelated/private.json"):
            path = self.repo / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"never export")
        self.names.add("tools/demo-lab/secret.pem")
        self.names.add("tools/demo-lab/runtime/leaked.json")
        result = module.export_context(self.repo, self.output)
        raw = (self.output / "source-export.json").read_bytes()
        manifest = json.loads(raw)
        self.assertEqual(result["manifest_sha256"], hashlib.sha256(raw).hexdigest())
        self.assertEqual(set(manifest["files"]), module.REQUIRED)
        self.assertIn("tools/demo-lab/container/Dockerfile", manifest["source_hashes"])
        self.assertIn("tools/demo-lab/container/demo-container-worker", manifest["source_hashes"])
        for name, item in manifest["files"].items():
            self.assertEqual(item["sha256"], hashlib.sha256((self.output / name).read_bytes()).hexdigest())

    def test_required_missing_bytes_bound_existing_and_nested_output(self):
        with self.assertRaises(ValueError):
            module.export_context(self.repo, self.output, max_bytes=1)
        self.assertFalse(self.output.exists())
        with self.assertRaises(ValueError):
            module.export_context(self.repo, self.repo / "nested")
        self.output.mkdir()
        with self.assertRaises(ValueError):
            module.export_context(self.repo, self.output)
        missing = next(iter(module.REQUIRED))
        (self.repo / missing).unlink()
        with self.assertRaises((ValueError, FileNotFoundError)):
            module.export_context(self.repo, self.base / "new")

    def test_symlink_rejected(self):
        target = self.repo / "tools/demo-lab/demo.py"
        target.unlink()
        try:
            target.symlink_to(self.repo / "tools/demo-lab/fixturegen/go.mod")
        except OSError as exc:
            self.skipTest(str(exc))
        with self.assertRaises(ValueError):
            module.export_context(self.repo, self.output)


    def test_drift_leaves_no_success_manifest(self):
        original = module.read_source
        counts = {}
        def changing(path):
            counts[path] = counts.get(path, 0) + 1
            data = original(path)
            return data + b"changed" if counts[path] > 1 else data
        with patch.object(module, "read_source", side_effect=changing):
            with self.assertRaises(ValueError):
                module.export_context(self.repo, self.output)
        self.assertTrue(self.output.exists())
        self.assertFalse((self.output / "source-export.json").exists())
    def test_noncanonical_path_rejected(self):
        for name in ("../private", "/absolute", "tools/demo-lab/../secret",
                     "tools/demo-lab/C:secret", "tools\\demo-lab\\a.py"):
            with self.assertRaises(ValueError):
                module.selected(name)


if __name__ == "__main__":
    unittest.main()
