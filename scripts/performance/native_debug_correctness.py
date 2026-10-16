"""Explicit local debug correctness provenance; never a benchmark qualification."""

import hashlib
import json
import re
import subprocess

from scripts.performance.linux_b5_ceiling import NAMES, require
from scripts.performance.linux_loopback import digest

FIELD = "debug_correctness_manifest_sha256"
CLASS = "DEBUG_CORRECTNESS_ONLY"
FIXTURES = (
    "vectors/wp8-f75-route-open/route-open-body.cbor",
    "vectors/wp8-local-admission/source.cose",
    "vectors/wp8-local-admission/destination.cose",
)


def validate_pin(pin):
    require(pin is None or (type(pin) is str and re.fullmatch("[0-9a-f]{64}", pin)), "explicit debug correctness manifest SHA256 required")
    return pin


def manifest_digest(build):
    return hashlib.sha256(json.dumps(build, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def source_inventory(root):
    names = (
        subprocess.check_output(
            [
                "git",
                "ls-files",
                "-z",
                "--",
                "crates/nbsr-transport/src",
                "crates/nbsr-transport/Cargo.toml",
                "crates/nbsr-transport/Cargo.lock",
                "crates/nbsr-transport/build.rs",
            ],
            cwd=root,
        )
        .decode()
        .split("\0")
    )
    names = sorted(set(filter(None, names)) | set(FIXTURES))
    require("crates/nbsr-transport/Cargo.lock" in names, "complete tracked build-source inventory required")
    for name in names:
        path = root / name
        require(not any(p.is_symlink() for p in (path, *path.parents)), "source alias rejected")
    return {name: digest(root / name) for name in names}


def validate_build(build, sha, hashes, pin=None, *, actual_source=None):
    validate_pin(pin)
    if pin is None:
        require(
            build.get("source_sha") == sha
            and build.get("build_profile") == "release"
            and build.get("binary_sha256") == hashes
            and build.get("build_commands")
            and build.get("toolchains"),
            "exact current release build manifest required",
        )
        return
    require(manifest_digest(build) == pin, "debug provenance pin mismatch")
    require(
        build.get("schema") == "nbsr-debug-correctness-build-v1"
        and build.get("build_profile") == "debug"
        and build.get("runtime_source_sha") == sha
        and type(build.get("source_sha")) is str
        and re.fullmatch("[0-9a-f]{40}", build["source_sha"])
        and build.get("binary_sha256") == hashes
        and set(hashes) == set(NAMES.values())
        and all(type(h) is str and re.fullmatch("[0-9a-f]{64}", h) for h in hashes.values())
        and type(build.get("build_commands")) is list
        and build["build_commands"]
        and type(build.get("toolchains")) is dict
        and build["toolchains"]
        and build.get("evidence_class") == CLASS,
        "debug build provenance mismatch",
    )
    inventory = build.get("source_sha256")
    required = {"crates/nbsr-transport/Cargo.toml", "crates/nbsr-transport/Cargo.lock", "crates/nbsr-transport/src/lib.rs", *FIXTURES}
    require(
        type(inventory) is dict
        and required <= inventory.keys()
        and all(
            type(n) is str
            and (n.startswith("crates/nbsr-transport/") or n in FIXTURES)
            and "\\" not in n
            and ":" not in n
            and not any(p in ("", ".", "..") for p in n.split("/"))
            and type(h) is str
            and re.fullmatch("[0-9a-f]{64}", h)
            for n, h in inventory.items()
        ),
        "debug source inventory required",
    )
    require(actual_source is None or inventory == actual_source, "debug current source inventory mismatch")


def qualification(pin):
    validate_pin(pin)
    return (
        {FIELD: pin, "evidence_class": CLASS, "throughput_benchmark": "INELIGIBLE", "capacity_benchmark": "INELIGIBLE"}
        if pin is not None
        else {}
    )


def status(normal, pin):
    validate_pin(pin)
    return normal + "_DEBUG_CORRECTNESS" if pin is not None else normal


def validate_workload(cell, post_close, pin):
    validate_pin(pin)
    if pin is not None:
        require(
            cell["path"] == "nbsr"
            and cell["streams"] == 2
            and cell["outstanding"] == 1
            and cell["cores"] == 1
            and post_close is True
            and "diagnostic_seconds" not in cell,
            "debug correctness requires short two-stream NBSR depth-one single-core cleanup workload",
        )
