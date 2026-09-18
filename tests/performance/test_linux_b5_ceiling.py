import hashlib
import json
from pathlib import Path
import shutil

import pytest

from scripts.performance import linux_b5_ceiling as ceiling
from scripts.performance.linux_b5_reference import OBSERVER, commands, finish_record
from scripts.performance.post_close_cleanup import FIELDS


SHA = "a" * 40
SHAPE = dict(physical_cores=1, endpoint_groups=1, runtime_workers=1, payload_bytes=16384, streams_per_group=1)
LINUX = dict(
    kernel="Linux test",
    python="3.14.6",
    taskset="/usr/bin/taskset",
    taskset_version="2",
    lscpu_version="2",
    selected_cpus=[0],
    inherited_cpus=[0],
    topology={"cpus": [dict(cpu=0, core=0, socket=0, node=0, online=True)]},
    cgroup_observed={
        f"/sys/fs/cgroup/{k}": v
        for k, v in {"cpu.max": "max 100000", "cpuset.cpus.effective": "0", "memory.max": "max", "pids.max": "max"}.items()
    },
)
SOURCE_FILES = (
    "linux_b5_reference.py",
    "linux_b5_ceiling.py",
    "linux_loopback.py",
    "b3_linux.py",
    "b4_linux.py",
    "linux_resources.py",
    "p2a_established.py",
    "physical_core_analysis.py",
    "post_close_cleanup.py",
    "authority.py",
)


def test_two_cpu_diagnostic_identity_preserves_single_cpu_reference_default():
    from copy import deepcopy
    linux = deepcopy(LINUX)
    linux['selected_cpus'] = linux['inherited_cpus'] = [0, 1]
    linux['topology']['cpus'].append(dict(cpu=1, core=1, socket=0, node=0, online=True))
    linux['cgroup_observed']['/sys/fs/cgroup/cpuset.cpus.effective'] = '0-1'
    assert ceiling.identity(linux, selected_count=2)['selected_cpus'] == [0, 1]
    with pytest.raises(ValueError, match='selected CPU'):
        ceiling.identity(linux)
    linux['cgroup_observed']['/sys/fs/cgroup/cpu.max'] = '100000 100000'
    with pytest.raises(ValueError, match='quota below'):
        ceiling.identity(linux, selected_count=2)


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value) + "\n")


def index(root):
    (root / "checksums.sha256").write_text(
        "".join(
            hashlib.sha256(p.read_bytes()).hexdigest() + "  " + p.relative_to(root).as_posix() + "\n"
            for p in sorted(root.rglob("*"))
            if p.is_file() and p.name != "checksums.sha256"
        )
    )


def fixture(root):
    sources = {}
    for name in SOURCE_FILES:
        relative = "scripts/performance/" + name
        contents = (Path(__file__).resolve().parents[2] / relative).read_bytes()
        retained = root / "source" / relative
        retained.parent.mkdir(parents=True, exist_ok=True)
        retained.write_bytes(contents)
        sources[relative] = hashlib.sha256(contents).hexdigest()
    binaries = {}
    names = {"direct": "perf_direct_peer", "nbsr": "perf_rust_source", "server": "wp8_interop_server"}
    for role, name in names.items():
        path = root / "binaries" / name
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(name.encode())
        binaries[role] = hashlib.sha256(path.read_bytes()).hexdigest()
    build = dict(
        source_sha=SHA,
        build_profile="release",
        build_commands=["recorded release command"],
        toolchains={"rustc": "recorded toolchain"},
        binary_sha256={names[r]: h for r, h in binaries.items()},
    )
    write(root / "build-manifest.json", build)
    write(
        root / "environment.json",
        dict(
            schema="nbsr-linux-b5-reference-v1",
            repository_sha=SHA,
            git_status="",
            classification="REFERENCE_CANDIDATE",
            shape=SHAPE,
            binary_sha256=binaries,
            linux_environment=LINUX,
            observer=OBSERVER,
            source_sha256=sources,
            workload=dict(depths=[1], warmup_seconds=3, duration_seconds=20),
            executable_paths={role: str(root / "binaries" / name) for role, name in names.items()},
        ),
    )
    rows = []
    for path in ("direct", "nbsr"):
        for repeat in range(1, 4):
            raw = root / f"raw/{path}-d1-r{repeat}"
            raw.mkdir(parents=True)
            value = dict(
                schema="nbsr-p2a-repeat-v2",
                path=path,
                streams=1,
                payload_bytes=16384,
                outstanding_per_stream=1,
                configured_total_outstanding=1,
                max_outstanding_per_stream_observed=1,
                completed_operations=100,
                measured_ns=1_000_000_000,
                p50_latency_ns=1,
                p95_latency_ns=2,
                p99_latency_ns=3,
                **dict.fromkeys(
                    (
                        "errors",
                        "missing",
                        "duplicates",
                        "corrupt",
                        "wrong_request",
                        "transport_sessions_created_delta",
                        "service_channels_created_delta",
                        "application_streams_created_delta",
                        "replay_entries_delta",
                    ),
                    0,
                ),
            )
            write(raw / "client.stdout", value)
            row = finish_record(dict(path=path, cores=1, streams=1, payload_bytes=16384, outstanding=1), repeat, value, cleanup_pass=True)
            row.update(
                raw_directory=raw.relative_to(root).as_posix(),
                observer=OBSERVER,
                process_ids={"client": 12, "server": 11},
                process_exit_codes={"client": 0, "server": 0},
                cleanup_reports=[],
            )
            cell = dict(path=path, cores=1, streams=1, payload_bytes=16384, outstanding=1)
            server, client, overrides = commands(cell, root / "binaries", root / "authority", raw, "127.0.0.1:42", 3, 20)
            prefix = ["/usr/bin/taskset", "--cpu-list", "0"]
            write(
                raw / "commands.json",
                dict(server=prefix + server, client=prefix + client, environment_overrides=overrides, selected_cpus=[0]),
            )
            write(raw / "ready.json", dict(endpoint="127.0.0.1:42"))
            (raw / "completion.ack").write_bytes(b"source sample flushed, joined, final and requested cleanup validated\n")
            samples = [
                dict(role=role, pid=pid, affinity=[0], start_ticks=pid, timestamp_ns=t, cpu_ns=t, state=state)
                for role, pid, t, state in (("server", 11, 1, "S"), ("client", 12, 2, "S"), ("client", 12, 3, "Z"), ("server", 11, 4, "Z"))
            ]
            (raw / "resources.ndjson").write_text("".join(json.dumps(s) + "\n" for s in samples))
            row["final_process_samples"] = {s["role"]: {k: v for k, v in s.items() if k != "role"} for s in samples if s["state"] == "Z"}
            row["resource_records"] = 4
            row["lifetime_cpu_ns"] = 7
            if path == "nbsr":
                for role, stem, pid in [("source", "client", 12), ("destination", "server", 11)]:
                    write(
                        raw / f"{stem}.cleanup.json",
                        dict(
                            schema="nbsr-p2a-post-close-v1",
                            role=role,
                            pid=pid,
                            diagnostics_enabled_before_run=True,
                            runtime_state="runtime_alive",
                            ownership=dict.fromkeys(FIELDS, 0),
                        ),
                    )
                    row["cleanup_reports"].append(dict(role=role, pid=pid, file=f"{stem}.cleanup.json", all_11_zero=True))
            rows.append(row)
    write(root / "records.json", rows)
    index(root)
    return binaries


def load(root, binaries, **kw):
    return ceiling.load_reference(
        root, current_sha=SHA, binary_sha256=binaries, shape=SHAPE, linux_environment=LINUX, percent=75, depth=1, **kw
    )


def test_exact_rational_load_remains_observer_unqualified(tmp_path):
    binaries = fixture(tmp_path)
    value = load(tmp_path, binaries)
    assert (value["rate_numerator"], value["rate_denominator"]) == (75, 1)
    assert value["observer"]["qualification"] == "NOT_QUALIFIED_NO_MATCHED_COMPARISON"
    assert value["reference_repeats"] == 3


@pytest.mark.parametrize(
    "change",
    [
        "oldsha",
        "dirty",
        "shape",
        "placement",
        "kernel",
        "cgroup",
        "observer",
        "binary",
        "badrecord",
        "missingreport",
        "boolreport",
        "tamper",
    ],
)
def test_invalid_reference_cannot_qualify(tmp_path, change):
    binaries = fixture(tmp_path)
    env = json.loads((tmp_path / "environment.json").read_text())
    if change == "oldsha":
        env["repository_sha"] = "b" * 40
    elif change == "dirty":
        env["git_status"] = " M changed"
    elif change == "shape":
        env["shape"]["runtime_workers"] = 4
    elif change == "placement":
        env["linux_environment"]["selected_cpus"] = [1]
    elif change == "kernel":
        env["linux_environment"]["kernel"] = "other"
    elif change == "cgroup":
        env["linux_environment"]["cgroup_observed"]["/sys/fs/cgroup/cpu.max"] = "10000 100000"
    elif change == "observer":
        env["observer"]["cadence_ns"] = 200_000_000
    elif change == "binary":
        (tmp_path / "binaries/perf_rust_source").write_bytes(b"other")
    elif change == "badrecord":
        rows = json.loads((tmp_path / "records.json").read_text())
        rows[-1]["valid"] = False
        write(tmp_path / "records.json", rows)
    elif change == "missingreport":
        (tmp_path / "raw/nbsr-d1-r1/client.cleanup.json").unlink()
    elif change == "boolreport":
        p = tmp_path / "raw/nbsr-d1-r1/client.cleanup.json"
        r = json.loads(p.read_text())
        r["ownership"]["pending_routes_current_entries"] = False
        write(p, r)
    else:
        (tmp_path / "raw/nbsr-d1-r1/client.stdout").write_text("{}\n")
    write(tmp_path / "environment.json", env)
    if change != "tamper":
        index(tmp_path)
    with pytest.raises(ValueError):
        load(tmp_path, binaries)


def test_too_few_or_dispersed_repeats_rejected(tmp_path):
    binaries = fixture(tmp_path)
    rows = json.loads((tmp_path / "records.json").read_text())
    write(tmp_path / "records.json", rows[:-1])
    index(tmp_path)
    with pytest.raises(ValueError):
        load(tmp_path, binaries)


@pytest.mark.parametrize("change", ["missing", "altered"])
def test_reference_controller_sources_must_match_retained_and_current(tmp_path, change):
    binaries = fixture(tmp_path)
    env = json.loads((tmp_path / "environment.json").read_text())
    key = "scripts/performance/linux_b5_reference.py"
    if change == "missing":
        del env["source_sha256"][key]
    else:
        retained = tmp_path / "source" / key
        retained.write_bytes(b"# altered controller\n")
        env["source_sha256"][key] = hashlib.sha256(retained.read_bytes()).hexdigest()
    write(tmp_path / "environment.json", env)
    index(tmp_path)
    with pytest.raises(ValueError, match="source"):
        load(tmp_path, binaries)


@pytest.mark.parametrize(
    "fault",
    [
        "no-baseline",
        "omitted-depth",
        "duplicate-raw",
        "missing-commands",
        "missing-resources",
        "missing-ack",
        "affinity",
        "pid",
        "start",
        "time",
        "cpu",
        "terminal",
        "final",
        "command-workers",
        "command-duration",
        "duplicate-flag",
    ],
)
def test_reference_requires_complete_ladder_and_bound_execution_evidence(tmp_path, fault):
    binaries = fixture(tmp_path)
    rows = json.loads((tmp_path / "records.json").read_text())
    env = json.loads((tmp_path / "environment.json").read_text())
    raw = tmp_path / rows[0]["raw_directory"]
    if fault == "no-baseline":
        env["workload"]["depths"] = [2]
    elif fault == "omitted-depth":
        env["workload"]["depths"] = [1, 2]
    elif fault == "duplicate-raw":
        rows[1]["raw_directory"] = rows[0]["raw_directory"]
    elif fault.startswith("missing-"):
        filename = {"missing-commands": "commands.json", "missing-resources": "resources.ndjson", "missing-ack": "completion.ack"}[fault]
        (raw / filename).unlink()
    elif fault.startswith("command-") or fault == "duplicate-flag":
        value = json.loads((raw / "commands.json").read_text())
        if fault == "duplicate-flag":
            value["client"] += ["--p2a-runtime-workers", "1"]
        else:
            flag = "--p2a-runtime-workers" if fault == "command-workers" else "--p2a-duration-seconds"
            value["client"][value["client"].index(flag) + 1] = "4"
        write(raw / "commands.json", value)
    elif fault == "final":
        rows[0]["final_process_samples"]["client"]["cpu_ns"] += 1
    else:
        samples = [json.loads(line) for line in (raw / "resources.ndjson").read_text().splitlines()]
        field, value = {
            "affinity": ("affinity", [1]),
            "pid": ("pid", 999),
            "start": ("start_ticks", 999),
            "time": ("timestamp_ns", 1),
            "cpu": ("cpu_ns", 0),
            "terminal": ("state", "S"),
        }[fault]
        samples[2][field] = value
        (raw / "resources.ndjson").write_text("".join(json.dumps(s) + "\n" for s in samples))
    write(tmp_path / "environment.json", env)
    write(tmp_path / "records.json", rows)
    index(tmp_path)
    with pytest.raises(ValueError):
        load(tmp_path, binaries)


@pytest.mark.parametrize("nbsr_repeats", [3, 4, 5])
def test_first_three_dispersion_requires_five_on_both_paths(tmp_path, nbsr_repeats):
    binaries = fixture(tmp_path)
    rows = json.loads((tmp_path / "records.json").read_text())
    for path, count in [("direct", 5), ("nbsr", nbsr_repeats)]:
        template = next(r for r in rows if r["path"] == path)
        for repeat in range(4, count + 1):
            row = json.loads(json.dumps(template))
            old = tmp_path / row["raw_directory"]
            row["raw_directory"] = f"raw/{path}-d1-r{repeat}"
            row["repeat"] = repeat
            shutil.copytree(old, tmp_path / row["raw_directory"])
            copied_commands = tmp_path / row["raw_directory"] / "commands.json"
            vectors = json.loads(copied_commands.read_text())
            for role in ("server", "client"):
                vectors[role] = [v.replace(str(old), str(tmp_path / row["raw_directory"])) for v in vectors[role]]
            write(copied_commands, vectors)
            rows.append(row)
    for row in rows:
        if row["path"] == "direct":
            record = row["binary_record"] | {"completed_operations": {1: 94, 2: 100, 3: 106}.get(row["repeat"], 100)}
            row.update(
                finish_record(
                    dict(path="direct", cores=1, payload_bytes=16384, streams=1, outstanding=1), row["repeat"], record, cleanup_pass=True
                )
            )
            write(tmp_path / row["raw_directory"] / "client.stdout", record)
    write(tmp_path / "records.json", rows)
    index(tmp_path)
    if nbsr_repeats == 5:
        assert load(tmp_path, binaries)["reference_repeats"] == 5
    else:
        with pytest.raises(ValueError, match="repeat"):
            load(tmp_path, binaries)
