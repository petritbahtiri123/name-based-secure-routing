"""Explicit dependency fetching, never called by check or offline build."""
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

from build_image import PIN, reviewed_pins


def main():
    pins = reviewed_pins(Path(__file__).with_name("official-image-pins.json"))
    for key, repository in (("GO_IMAGE", "golang"), ("RUST_IMAGE", "rust"),
                            ("PYTHON_IMAGE", "python")):
        value = os.environ.get(key, "")
        role = {"GO_IMAGE": "go", "RUST_IMAGE": "rust", "PYTHON_IMAGE": "python"}[key]
        if value != pins[role]["reference"]:
            raise ValueError("Preparation input differs from reviewed official pin")
        if not PIN.fullmatch(value) or not value.startswith(f"docker.io/library/{repository}@sha256:"):
            raise ValueError(f"{key} requires reviewed official repository digest")
    if platform.system() != "Linux" or not (3, 12) <= sys.version_info[:2] < (3, 15):
        raise ValueError("Unsupported preparation platform/Python")
    machine = {"x86_64": "amd64", "aarch64": "arm64"}.get(platform.machine())
    if machine is None or machine != os.environ.get("TARGETARCH"):
        raise ValueError("Native architecture required")
    for args, prefix in ((["go", "version"], "go version go1.26.5 "),
                         (["rustc", "--version"], "rustc 1.97.1 "),
                         (["cargo", "--version"], "cargo 1.97.1 ")):
        if not subprocess.check_output(args, text=True, timeout=5).startswith(prefix):
            raise ValueError("Required exact toolchain missing")
    subprocess.run(["cc", "--version"], check=True, timeout=5)
    from nbsr_demo_lab.setup import guarded, inventory, environment
    repo = Path("/src")
    before = inventory(repo)
    env = environment()
    env.update(GOPROXY="https://proxy.golang.org", GOSUMDB="sum.golang.org",
               CARGO_NET_OFFLINE="false", GOFLAGS="-mod=readonly")
    for index, module in enumerate(("client/nbsr-go-client/demo",
                                    "client/nbsr-go-client", "interop/nbsr-go-peer")):
        guarded([shutil.which("go"), "mod", "download"], repo / module, env,
                Path("/opt/nbsr-prepare") / f"go-{index}")
    guarded([shutil.which("cargo"), "fetch", "--locked", "--manifest-path",
             str(repo / "crates/nbsr-transport/Cargo.toml")], repo, env,
            Path("/opt/nbsr-prepare/rust"))
    if before != inventory(repo):
        raise ValueError("Preparation changed locked source")


if __name__ == "__main__":
    main()
