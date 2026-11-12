import importlib.util
import unittest
import json
import tempfile
from pathlib import Path

spec = importlib.util.spec_from_file_location("image_build", Path(__file__).with_name("build_image.py"))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class PackagingContract(unittest.TestCase):
    def test_pins_and_native_arch_required(self):
        pin = "reviewed.example/nbsr/toolchain@sha256:" + "a" * 64
        source = "b" * 40
        for target, machine in (("amd64", "x86_64"), ("arm64", "aarch64")):
            module.validate_metadata(pin, source, target, machine)
        for base, commit, target, machine in (
            ("latest", source, "amd64", "x86_64"),
            (pin, "unknown", "amd64", "x86_64"),
            (pin, source, "amd64", "aarch64"),
            (pin, source, "arm64", "x86_64"),
            ("", source, "arm64", "aarch64"),
        ):
            with self.assertRaises(ValueError):
                module.validate_metadata(base, commit, target, machine)


    def test_reviewed_pins_match_recipe_and_reject_drift(self):
        path = Path(__file__).with_name("official-image-pins.json")
        pins = module.reviewed_pins(path)
        self.assertEqual(set(pins), {"go", "rust", "python"})
        with tempfile.TemporaryDirectory() as directory:
            altered = json.loads(path.read_text(encoding="utf-8-sig"))
            altered["images"]["go"]["reviewed_tag"] = "latest"
            bad = Path(directory) / "pins.json"
            bad.write_text(json.dumps(altered))
            with self.assertRaises(ValueError):
                module.reviewed_pins(bad)
        recipe = Path(__file__).with_name("Prepare.Dockerfile").read_text(encoding="utf-8-sig")
        for argument in ("GO_IMAGE", "RUST_IMAGE", "PYTHON_IMAGE"):
            self.assertIn("ARG " + argument, recipe)
    def test_no_implicit_fetch_or_runtime_privilege(self):
        dockerfile = Path(__file__).with_name("Dockerfile").read_text(encoding="utf-8-sig")
        self.assertIn("GOPROXY=off", dockerfile)
        self.assertIn("CARGO_NET_OFFLINE=true", dockerfile)
        self.assertIn("USER 65532:65532", dockerfile)
        self.assertNotIn("apt-get", dockerfile)
        self.assertNotIn("curl ", dockerfile)
        self.assertNotIn(":latest", dockerfile)


if __name__ == "__main__":
    unittest.main()
