"""Build a pinned PoC image pair and emit a validated Compose environment.

Does not start containers, alter Docker settings, repair Docker, or publish.
Base images must already be present locally by immutable repository digest.
"""

import argparse
import hashlib
import ipaddress
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
PIN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]*@sha256:[0-9a-f]{64}\Z")


def validate_image(value):
    if not PIN.fullmatch(value):
        raise ValueError("immutable repository image digest required")
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("go-image", "rust-image", "python-image"):
        parser.add_argument("--" + name, required=True, type=validate_image)
    parser.add_argument("--private-cidr", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not re.fullmatch(r"nbsr-isp-poc-[a-z0-9-]{1,40}", args.run_id) or args.run_id.endswith("-"):
        parser.error("unique bounded nbsr-isp-poc run ID required")
    subnet = ipaddress.IPv4Network(args.private_cidr, strict=True)
    if not any(subnet.subnet_of(ipaddress.IPv4Network(parent)) for parent in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")):
        parser.error("dedicated RFC1918 IPv4 subnet required")
    sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    if subprocess.check_output(["git", "status", "--porcelain", "--untracked-files=all"], cwd=ROOT, text=True):
        parser.error("clean accepted checkout required")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    commands = []

    def command(argv):
        ordinal = len(commands)
        result = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True, timeout=1800)
        (output / f"{ordinal:02d}.stdout").write_text(result.stdout)
        (output / f"{ordinal:02d}.stderr").write_text(result.stderr)
        commands.append({"argv": argv, "exit_code": result.returncode})
        (output / "commands.json").write_text(json.dumps(commands, indent=2) + "\n")
        if result.returncode:
            raise RuntimeError("command failed; raw output retained")
        return result.stdout

    bases = {"GO_IMAGE": args.go_image, "RUST_IMAGE": args.rust_image, "PYTHON_IMAGE": args.python_image}
    for reference in bases.values():
        inspected = json.loads(command(["docker", "image", "inspect", reference]))
        if len(inspected) != 1 or reference not in inspected[0].get("RepoDigests", []):
            raise ValueError("base image digest not available locally")
    # Reject a requested subnet already occupied by any existing Docker network.
    networks = command(["docker", "network", "ls", "--quiet"]).split()
    if networks:
        for network in json.loads(command(["docker", "network", "inspect", *networks])):
            for entry in network.get("IPAM", {}).get("Config", []) or []:
                if "Subnet" in entry:
                    existing = ipaddress.ip_network(entry["Subnet"])
                    if existing.version == 4 and existing.overlaps(subnet):
                        raise ValueError("private subnet overlaps an existing Docker network")
    images = {}
    for target in ("runtime", "adapter"):
        tag = f"{args.run_id}-{target}:{sha}"
        argv = [
            "docker",
            "build",
            "--pull=false",
            "--file",
            "deploy/isp-federation-poc/Dockerfile",
            "--target",
            target,
            "--tag",
            tag,
            "--build-arg",
            "SOURCE_SHA=" + sha,
        ]
        for key, value in bases.items():
            argv += ["--build-arg", key + "=" + value]
        command([*argv, "."])
        image = json.loads(command(["docker", "image", "inspect", tag]))[0]
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", image["Id"]):
            raise ValueError("invalid built image ID")
        images[target] = image["Id"]
    environment = {
        "NBSR_ISP_RUNTIME_IMAGE": images["runtime"],
        "NBSR_ISP_ADAPTER_IMAGE": images["adapter"],
        "NBSR_ISP_RUN_ID": args.run_id,
        "NBSR_SOURCE_SHA": sha,
        "ISP_B_PRIVATE_CIDR": str(subnet),
    }
    env_path = output / "compose.env"
    env_path.write_text("".join(f"{key}={value}\n" for key, value in environment.items()))
    compose = [
        "docker",
        "compose",
        "--env-file",
        str(env_path),
        "--project-name",
        args.run_id,
        "--file",
        "deploy/isp-federation-poc/compose.yaml",
    ]
    command([*compose, "config", "--quiet"])
    if subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip() != sha or subprocess.check_output(
        ["git", "status", "--porcelain", "--untracked-files=all"], cwd=ROOT, text=True
    ):
        raise ValueError("source checkout changed during build")
    (output / "manifest.json").write_text(
        json.dumps(
            {
                "source_sha": sha,
                "bases": bases,
                "images": images,
                "private_cidr": str(subnet),
                "project": args.run_id,
                "status": "BUILD_AND_CONFIG_ONLY",
                "validation_command": [sys.executable, "deploy/isp-federation-poc/run_isolation.py",
                                       "--prepared", str(output / "manifest.json"),
                                       "--output", str(output.with_name(output.name + "-validation"))],
                "cleanup_policy": "Validated orchestrator preserves child logs before exact-ID teardown; failed export retains resources.",
                "live_validation": "NOT_RUN",
            },
            indent=2,
        )
        + "\n"
    )
    files = sorted(p for p in output.iterdir() if p.is_file())
    (output / "checksums.sha256").write_text("".join(hashlib.sha256(p.read_bytes()).hexdigest() + "  " + p.name + "\n" for p in files))


if __name__ == "__main__":
    main()
