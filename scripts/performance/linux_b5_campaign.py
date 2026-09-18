"""Linux B5 execution entrypoint; accounting is not observer-qualified stability."""

import argparse
import json
import math
import os
from pathlib import Path
import shutil
import statistics
import tempfile

from scripts import run_b5_v2 as shared
from scripts.performance.authority import write_loopback_authority
from scripts.performance.b3_linux import environment
from scripts.performance.linux_b5_backend import LinuxB5Backend
from scripts.performance.linux_b5_ceiling import NAMES, identity, load_reference, require
from scripts.performance.linux_b5_reference import SOURCE_PATHS as REFERENCE_SOURCES, git_state
from scripts.performance.linux_loopback import ROOT, checksums, digest, write_json
from scripts.performance.process_cancellation import Cancellation, not_cancelled

SOURCE_PATHS = tuple(dict.fromkeys((*REFERENCE_SOURCES,
    "scripts/run_b5_v2.py", "scripts/run_max_throughput_v2_stage4.py",
    "scripts/run_p2a_established.py", "scripts/run_physical_core_v2.py",
    "scripts/run_performance_validation.py", "scripts/profile_b2_v2.py",
    *("scripts/performance/" + name for name in (
        "linux_b5_campaign.py", "linux_b5_backend.py", "linux_exit.py", "process_cancellation.py",
        "b5_stream.py", "b5_ownership.py", "b5_ceiling.py", "resources.py", "sustained_capacity.py")))))


def cv(values):
    if any(type(v) not in (int, float) or not math.isfinite(v) or v <= 0 for v in values):
        raise ValueError("positive finite cohort metric required")
    return statistics.stdev(values) / statistics.mean(values) if len(values) > 1 else 0.0


def run_cohort(paths, run, retain, *, diagnostic):
    paths = shared.selected_paths(paths)
    required = 1 if diagnostic else 3
    rows = {path: [] for path in paths}
    for repeat in range(1, 6):
        if repeat > required:
            break
        for path in shared.path_order(paths, repeat):
            row = run(path, repeat)
            retain(row)
            if row.get("valid") is not True:
                raise RuntimeError("invalid partial run retained; no replacement")
            rows[path].append(row)
        if repeat == 3:
            if any(cv([r.get(field) for r in values]) > .05
                   for values in rows.values() for field in ("gbps", "window_p99_median_ns")):
                required = 5
    return required


def execute(args, *, check_cancelled=not_cancelled):
    placement = getattr(args, 'placement', 'shared')
    require(placement in ('shared', 'split'), 'unknown placement')
    require(placement != 'split' or args.diagnostic, 'split placement requires diagnostic mode')
    selected_count = 2 if placement == 'split' else 1
    mode = shared.validate_mode(diagnostic=args.diagnostic, reference=args.reference, rate=args.rate)
    retain_failed = getattr(args, 'retain_failed_diagnostic', False)
    require(not retain_failed or (args.diagnostic and 0 < args.duration <= 600),
            'retention requires diagnostic mode and at most 600 seconds')
    paths = shared.selected_paths(args.paths)
    require(type(args.streams) is int and 1 <= args.streams <= 64, "streams must be1-64")
    require(args.payload in (1024, 16384) and args.depth in (1, 2, 4, 8, 16), "unsupported payload/depth")
    require(math.isfinite(args.warmup) and args.warmup >= 3
            and math.isfinite(args.duration) and 0 < args.duration <= 7200
            and math.isfinite(args.progress) and 1 <= args.progress <= args.duration, "invalid phase bounds")
    require(args.diagnostic or args.duration in (600, 1800, 3600, 7200), "reference-bound stages are10/30/60/120minutes")
    sha, dirty = git_state()
    require(not dirty, "clean checkout required")
    output, binary_root = args.output.resolve(), args.binaries.resolve()
    require(not output.is_relative_to(ROOT), "evidence must be outside checkout")
    binaries = {role: binary_root / name for role, name in NAMES.items()}
    hashes = {role: digest(path) for role, path in binaries.items()}
    build = json.loads(args.build_manifest.read_bytes())
    require(build.get("source_sha") == sha and build.get("build_profile") == "release"
            and build.get("build_commands") and build.get("toolchains"), "current release build manifest required")
    require(build.get("binary_sha256") == {NAMES[r]: h for r, h in hashes.items()}, "binary hashes mismatch")
    require(all(os.access(p, os.X_OK) for p in binaries.values()), "executable binaries required")
    linux = environment(selected_count)
    initial_identity = identity(linux, selected_count=selected_count)
    backend = LinuxB5Backend(linux, placement=placement, check_cancelled=check_cancelled)
    shape = dict(physical_cores=selected_count, endpoint_groups=1, runtime_workers=1,
                 payload_bytes=args.payload, streams_per_group=args.streams)
    load = (dict(mode=mode, rate_numerator=args.rate[0], rate_denominator=args.rate[1]) if args.diagnostic else
            load_reference(args.reference, current_sha=sha, binary_sha256=hashes, shape=shape,
                           linux_environment=linux, percent=args.percent, depth=args.depth))
    plan = dict(source_mask=backend.mask, endpoint_masks=[backend.destination_mask],
                logical_processors_available=selected_count)
    sources = {path: digest(ROOT / path) for path in SOURCE_PATHS}
    output.mkdir(parents=True, exist_ok=False)
    rows = []
    metadata = dict(schema="nbsr-linux-b5-campaign-v1", repository_sha=sha, git_status="", mode=mode,
        binary_sha256=hashes, source_sha256=sources, source_scope="listed controllers plus entire clean Git SHA",
        linux_environment=linux, shape=shape, load=load, placement=plan,
        cpu_allocation=dict(placement=placement, selected_guest_cpus=selected_count,
                            per_peer_guest_cpus=1, verified_host_physical_cores=False),
        observer_qualification="NOT_QUALIFIED", thermal_and_power="NOT_MEASURED",
        controller_args={k: str(v) if isinstance(v, Path) else v for k, v in vars(args).items()},
        scope=backend.scope)

    def unchanged():
        check_cancelled()
        require(git_state() == (sha, ""), "source checkout changed")
        require(all(digest(ROOT / p) == h for p, h in sources.items()), "source bytes changed")
        require(all(digest(binaries[r]) == h and digest(output / "binaries" / NAMES[r]) == h
                    for r, h in hashes.items()), "binary bytes changed")
        require(identity(environment(selected_count), selected_count=selected_count) == initial_identity,
                "Linux placement/cgroup changed")

    def retain(row):
        rows.append(row)
        write_json(output / "records.json", rows)

    try:
        write_json(output / "environment.json", metadata)
        write_json(output / "build-manifest.json", build)
        (output / "binaries").mkdir()
        for role, binary in binaries.items():
            shutil.copy2(binary, output / "binaries" / NAMES[role])
        for relative in sources:
            target = output / "source" / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / relative, target)
        with tempfile.TemporaryDirectory(prefix="nbsr-linux-b5-") as temporary:
            authority = Path(temporary) / "authority"
            write_loopback_authority(authority)

            def run(path, repeat):
                unchanged()
                relative = f"raw/{path}-r{repeat}"
                cell = dict(path=path, endpoint_groups=1, streams_per_group=args.streams,
                            outstanding_per_stream=args.depth, payload_bytes=args.payload)
                row = shared.run_one(cell, binaries, authority, plan, output / relative,
                    warmup=args.warmup, duration=args.duration, progress=args.progress,
                    rate=(load["rate_numerator"], load["rate_denominator"]), diagnostic=args.diagnostic,
                    ownership_sampling=args.ownership_sampling, backend=backend,
                    retain_failed_diagnostic=retain_failed)
                row["raw_directory"] = relative
                if row["valid"]:
                    values = []
                    with (output / relative / "source.stdout.ndjson").open() as stream:
                        for line in stream:
                            value = json.loads(line)
                            if value.get("event") == "b5_grouped_progress" and value.get("phase") == "steady":
                                if value.get("p99_latency_ns") is not None:
                                    values.append(value["p99_latency_ns"])
                    row["window_p99_median_ns"] = statistics.median(values) if values else None
                return row

            repeats = run_cohort(paths, run, retain, diagnostic=args.diagnostic)
        unchanged()
        dispersion = {path: {field: (cv([r[field] for r in rows if r["path"] == path])
                            if repeats >= 3 else None)
                            for field in ("gbps", "window_p99_median_ns")} for path in paths}
        write_json(output / "summary.json", dict(classification="DIAGNOSTIC" if args.diagnostic else "ACCOUNTING_PASS_QUALIFICATION_PENDING",
            repeats_per_path=repeats, paths=list(paths), observer_qualification="NOT_QUALIFIED",
            cohort_cv=dispersion, dispersion_unresolved=any(v is not None and v > .05
                for metrics in dispersion.values() for v in metrics.values()),
            p99_definition="median of steady-window p99, not pooled-operation p99",
            sustained_stability="NOT_PROVEN", external_server="NOT_PROVEN"))
    except Exception as error:
        write_json(output / "failure.json", dict(classification="INVALID_PARTIAL", error=str(error), retained=len(rows)))
        raise
    finally:
        write_json(output / "records.json", rows)
        checksums(output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("binaries", "build-manifest", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--reference", type=Path)
    parser.add_argument("--diagnostic", action="store_true")
    parser.add_argument("--placement", choices=("shared", "split"), default="shared",
                        help="split is diagnostic only; allocates one distinct guest CPU per peer")
    parser.add_argument("--retain-failed-diagnostic", action="store_true",
                        help="retain up to 600s after performance drift; failed gates remain FAIL")
    parser.add_argument("--rate", type=int, nargs=2)
    parser.add_argument("--paths", choices=("direct", "nbsr"), nargs="+", default=["direct", "nbsr"])
    parser.add_argument("--ownership-sampling", action="store_true")
    parser.add_argument("--percent", type=int, choices=range(70, 81), default=70)
    parser.add_argument("--payload", type=int, choices=(1024, 16384), default=1024)
    parser.add_argument("--streams", type=int, default=32)
    parser.add_argument("--depth", type=int, choices=(1, 2, 4, 8, 16), default=1)
    parser.add_argument("--warmup", type=float, default=3)
    parser.add_argument("--duration", type=float, required=True)
    parser.add_argument("--progress", type=float, default=30)
    args = parser.parse_args()
    with Cancellation() as cancellation:
        execute(args, check_cancelled=cancellation.check)


if __name__ == "__main__":
    main()
