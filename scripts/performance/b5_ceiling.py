"""Consume a current, hash-bound physical-core cohort for a paced soak load."""

from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path
import re
import statistics

from scripts.performance.physical_core_analysis import classify_ladder


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def topology_identity(topology):
    """Stable fields actually supplied by windows_processor_topology.

    These identify processor layout, not a unique host or CPU model. Do not
    manufacture a hardware identifier or compare timestamps/derived labels.
    """
    try:
        require(type(topology) is dict and topology["verified"] is True, "unverified topology")
        require(topology["scope"] == "physical-core-selected-logical-processors", "unsupported topology scope")
        physical, logical = topology["physical_cores"], topology["logical_processors"]
        require(type(physical) is int and physical > 0 and type(logical) is int and logical > 0, "invalid processor counts")
        require(type(topology["cores"]) is list and len(topology["cores"]) == physical, "missing core identity")
        cores, combined = [], 0
        for index, core in enumerate(topology["cores"]):
            require(type(core) is dict and type(core["core_index"]) is int and core["core_index"] == index, "invalid core index")
            require(type(core["smt"]) is bool and type(core["efficiency_class"]) is int and core["efficiency_class"] >= 0, "invalid core identity")
            mask = core["logical_mask"]
            require(type(mask) is int and mask > 0 and mask & combined == 0, "invalid core mask")
            combined |= mask
            cores.append({key: core[key] for key in ("core_index", "smt", "efficiency_class", "logical_mask")})
        require(combined.bit_count() == logical, "topology count mismatch")
        return {"scope": topology["scope"], "physical_cores": physical, "logical_processors": logical, "cores": cores}
    except (KeyError, TypeError) as error:
        raise ValueError("incomplete topology identity") from error


def placement_identity(value):
    try:
        require(type(value) is dict, "invalid reference placement")
        mask, count, endpoints = value["source_mask"], value["logical_processors_available"], value["endpoint_masks"]
        require(type(mask) is int and mask > 0 and type(count) is int and count > 0 and mask.bit_count() == count, "invalid source pool")
        require(type(endpoints) is list and len(endpoints) in (1, 2, 4)
                and all(type(v) is int and v == mask for v in endpoints), "reference requires matched shared pool")
        return {"source_mask": mask, "endpoint_masks": list(endpoints), "logical_processors_available": count}
    except (KeyError, TypeError) as error:
        raise ValueError("incomplete reference placement") from error


def load_ceiling(root, *, current_sha, binary_sha256, shape, percent, depth):
    """Recompute classification and derive the rate from exact operation counts.

    The caller supplies current binaries and verified intended topology/shape.
    This binds a load reference; it neither runs a soak nor accepts its outcome.
    """
    try:
        require(type(percent) is int and 70 <= percent <= 80, "invalid load percent")
        require(type(depth) is int and 1 <= depth <= 64, "invalid depth")
        require(isinstance(current_sha, str) and re.fullmatch(r"[0-9a-f]{40}", current_sha), "invalid SHA")
        keys = {"physical_cores", "endpoint_groups", "streams_per_group", "payload_bytes", "runtime_workers"}
        require(type(shape) is dict and set(shape) == keys, "invalid shape")
        require(all(type(v) is int and v > 0 for v in shape.values()), "invalid shape count")
        require(type(binary_sha256) is dict and set(binary_sha256) == {"direct", "nbsr", "server"}, "invalid binaries")
        require(all(isinstance(v, str) and re.fullmatch(r"[0-9a-f]{64}", v) for v in binary_sha256.values()), "invalid binary hash")
        root = Path(root).resolve()
        manifest = (root / "checksums.sha256").read_bytes()
        seen = set()
        inputs = {}
        for line in manifest.decode().splitlines():
            expected, relative = line.split("  ", 1)
            target = (root / relative).resolve()
            require(target.is_relative_to(root) and target not in seen, "invalid checksum path")
            require(re.fullmatch(r"[0-9a-f]{64}", expected), "invalid checksum")
            seen.add(target)
            if target in (root / "environment.json", root / "records.json"):
                content = target.read_bytes()
                require(hashlib.sha256(content).hexdigest() == expected, "checksum mismatch")
                inputs[target.name] = content
            else:
                with target.open("rb") as stream:
                    require(hashlib.file_digest(stream, "sha256").hexdigest() == expected, "checksum mismatch")
        require(all(root / name in seen for name in ("environment.json", "records.json")), "missing checksum input")
        env = json.loads(inputs["environment.json"])
        records = json.loads(inputs["records.json"])
        require(env["repository_sha"] == current_sha and env["git_status"] == "", "stale or dirty reference")
        require(env["binary_sha256"] == binary_sha256, "binary mismatch")
        require(env["topology"]["verified"] is True and env["smt_siblings_used"] is False, "unverified physical cores")
        require(type(env["physical_cores"]) is int and env["physical_cores"] == shape["physical_cores"], "physical-core mismatch")
        reference_topology = topology_identity(env["topology"])
        reference_placement = placement_identity(env["placement"])
        require(reference_placement["logical_processors_available"] == shape["physical_cores"]
                and len(reference_placement["endpoint_masks"]) == shape["endpoint_groups"], "placement shape mismatch")
        require(type(records) is list, "invalid records")
        rows = [r for r in records if r["path"] == "nbsr"]
        require(rows, "missing NBSR reference")
        exact_rates = {}
        for row in rows:
            require(all(type(row[k]) is int and row[k] == shape[k] for k in keys - {"physical_cores"}), "shape mismatch")
            completed, elapsed = row["completed_operations"], row["measured_ns"]
            require(type(completed) is int and completed > 0 and type(elapsed) is int and elapsed > 0, "invalid operation count")
            rate = Fraction(completed * 1_000_000_000, elapsed)
            for key, expected in (
                ("operations_per_second", rate),
                ("aggregate_application_gbps", rate * 16 * shape["payload_bytes"] / 1_000_000_000),
            ):
                require(
                    type(row[key]) in (int, float) and math.isfinite(row[key]) and math.isclose(row[key], float(expected), rel_tol=1e-12),
                    "count/rate mismatch",
                )
            exact_rates.setdefault(row["outstanding_per_stream"], []).append(rate)
        ladder = classify_ladder(rows)
        selected = [cell for cell in ladder["cells"] if cell["outstanding_per_stream"] == depth]
        require(len(selected) == 1 and selected[0]["classification"] == "STABLE", "reference is not strict stable")
        reference = statistics.median(exact_rates[depth])
        offered = reference * Fraction(percent, 100)
        require(0 < offered.numerator < 2**64 and 0 < offered.denominator < 2**64, "unrepresentable rate")
        return {
            "schema": "nbsr-b5-ceiling-load-v1",
            "reference_sha": current_sha,
            "manifest_sha256": hashlib.sha256(manifest).hexdigest(),
            "reference_repeats": selected[0]["repeat_count"],
            "reference_operations_per_second": float(reference),
            "reference_gbps": selected[0]["median_gbps"],
            "load_percent": percent,
            "rate_numerator": offered.numerator,
            "rate_denominator": offered.denominator,
            "shape": dict(shape),
            "outstanding_per_stream": depth,
            "binary_sha256": dict(binary_sha256),
            "reference_placement": reference_placement,
            "reference_topology_identity": reference_topology,
            "hardware_identity_scope": "TOPOLOGY_ONLY_NO_HOST_ID",
            "scope": "Current finite closed-loop reference; actual paced load/stability requires live validation.",
        }
    except (OSError, KeyError, TypeError, OverflowError, UnicodeError) as error:
        raise ValueError("invalid ceiling artifact") from error
