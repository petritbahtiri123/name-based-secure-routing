"""Offline image assembly. Called only by an explicit, supervised image build."""
import json
import os
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path

PIN = re.compile(r"[a-z0-9][a-z0-9./:_-]*@sha256:[0-9a-f]{64}")
ROLES = (
    ("authority", "client/nbsr-go-client/demo", "./cmd/nbsr-demo-authority", False),
    ("client", "client/nbsr-go-client/demo", "./cmd/nbsr-demo-client", False),
    ("backend", "client/nbsr-go-client/demo", "./cmd/nbsr-demo-backend", False),
    ("fixturegen", "tools/demo-lab/fixturegen", ".", False),
    ("test-client", "client/nbsr-go-client/demo", "./internal/client", True),
    ("test-corestate", "client/nbsr-go-client", "./internal/corestate", True),
    ("test-resolution", "client/nbsr-go-client", "./internal/resolution", True),
)



def reviewed_pins(path):
    data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if data.get("schema") != "nbsr-demo-official-image-pins-v1":
        raise ValueError("Invalid reviewed image pin schema")
    expected = {"go": ("golang", "1.26.5-bookworm"),
                "rust": ("rust", "1.97.1-bookworm"),
                "python": ("python", "3.13-bookworm")}
    if set(data.get("images", {})) != set(expected):
        raise ValueError("Incomplete reviewed image pins")
    for name, (repository, tag) in expected.items():
        image = data["images"][name]
        reference = image.get("reference", "")
        if not PIN.fullmatch(reference) or not reference.startswith(f"docker.io/library/{repository}@sha256:"):
            raise ValueError("Official immutable reference required")
        if image.get("reviewed_tag") != tag:
            raise ValueError("Recipe toolchain/release pin mismatch")
        architectures = image.get("architectures", {})
        if set(architectures) != {"amd64", "arm64"} or any(
            not re.fullmatch("sha256:[0-9a-f]{64}", value) for value in architectures.values()
        ):
            raise ValueError("Both native Linux architecture digests required")
    return data["images"]

def validate_metadata(base, source, target, machine):
    if not PIN.fullmatch(base):
        raise ValueError("A reviewed name@sha256 image digest is mandatory")
    if not re.fullmatch(r"[0-9a-f]{40}", source):
        raise ValueError("Exact source commit required")
    actual = {"x86_64": "amd64", "aarch64": "arm64"}.get(machine)
    if target not in {"amd64", "arm64"} or target != actual:
        raise ValueError("Native Linux amd64/arm64 only; emulation is not acceptance")


def main():
    validate_metadata(os.environ.get("BASE_IMAGE", ""), os.environ.get("SOURCE_SHA", ""),
                      os.environ.get("TARGETARCH", ""), platform.machine())
    if platform.system() != "Linux" or not (3, 12) <= sys.version_info[:2] < (3, 15):
        raise ValueError("Linux and Python >=3.12,<3.15 required")
    versions = {}
    for tool, prefix in (("go", "go version go1.26.5 "), ("rustc", "rustc 1.97.1 "),
                         ("cargo", "cargo 1.97.1 ")):
        args = [tool, "version" if tool == "go" else "--version"]
        version = subprocess.check_output(args, text=True, timeout=5).strip()
        if not version.startswith(prefix):
            raise ValueError(f"{tool} version mismatch")
        versions[tool] = version
    from nbsr_demo_lab.setup import digest, environment, guarded, inventory
    repo = Path("/src")
    state = Path("/opt/nbsr-image")
    binaries = Path("/opt/nbsr-build/nbsr-demo/image")
    state.mkdir(mode=0o755)
    binaries.mkdir(parents=True, mode=0o755)
    env = environment()
    env["GOFLAGS"] = "-mod=readonly"
    env["CARGO_TARGET_DIR"] = "/opt/nbsr-cache/cargo-target"
    before = inventory(repo)
    artifacts = {}
    for role, module, target, test in ROLES:
        path = binaries / role
        args = [shutil.which("go"), "test", "-c"] if test else [shutil.which("go"), "build"]
        guarded([*args, "-p", "2", "-trimpath", "-o", str(path), target],
                repo / module, env, state / ("log-" + role))
        artifacts[role] = {"path": str(path), "sha256": digest(path)}
    guarded([shutil.which("cargo"), "build", "--locked", "--offline", "--release", "--jobs", "2",
             "--manifest-path", str(repo / "crates/nbsr-transport/Cargo.toml"),
             "--bin", "wp8_interop_server"], repo, env, state / "log-rust")
    destination = binaries / "destination"
    shutil.copyfile(Path(env["CARGO_TARGET_DIR"]) / "release/wp8_interop_server", destination)
    artifacts["destination"] = {"path": str(destination), "sha256": digest(destination)}
    if before != inventory(repo):
        raise ValueError("Source changed during build")
    for artifact in artifacts.values():
        Path(artifact["path"]).chmod(0o555)
    manifest = {"artifacts": artifacts, "source_hashes": before,
                "source_commit": os.environ["SOURCE_SHA"],
                "platform": f"Linux-{platform.machine()}", "toolchain": versions}
    (state / "build.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (state / "container.json").write_text(json.dumps({
        "schema": "nbsr-demo-container-image-v1", "base_image": os.environ["BASE_IMAGE"],
        "execution_arch": os.environ["TARGETARCH"], "source_commit": os.environ["SOURCE_SHA"],
        "validation": "built only; no native Mac host acceptance"}), encoding="utf-8")
    for directory in ("/artifacts", "/opt/nbsr-build/nbsr-demo/runs",
                      "/src/client/nbsr-go-client/demo/test-results/nbsr-demo/runtime"):
        Path(directory).mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chown(directory, 65532, 65532)


if __name__ == "__main__":
    main()
