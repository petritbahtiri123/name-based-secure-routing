import json
from pathlib import PurePosixPath

import pytest

from scripts.performance.linux_b5_ceiling import NAMES
from scripts.performance.linux_b5_placement import seal_output
from scripts.performance.linux_loopback import digest
from scripts.performance.linux_native_lifecycle import command, validate_result
from scripts.performance.linux_native_lifecycle_pair import analyze
from scripts.performance.post_close_cleanup import FIELDS

SHA = "a" * 40


def write(root, name, value):
    (root / name).write_text(json.dumps(value))


def peers(tmp_path):
    roots = [tmp_path / r for r in ("source", "destination")]
    ready = dict(endpoint="192.0.2.2:4444", alpn="nbsr-quic-1")
    fixture = dict(
        certificates=dict.fromkeys(("ca.der", "source.der", "destination.der"), "b" * 64),
        service=dict.fromkeys(
            (
                "name.txt",
                "route-open-body.cbor",
                "federation-context.cbor",
                "source.cose",
                "destination.cose",
                "request-id.bin",
                "channel-id.bin",
                "route-id.bin",
                "grant-digest.bin",
            ),
            "c" * 64,
        ),
    )
    for role, root in zip(("source", "destination"), roots, strict=True):
        root.mkdir()
        (root / "executed-binary").write_bytes(b"executable fixture")
        hashes = dict.fromkeys(NAMES.values(), digest(root / "executed-binary"))
        env = dict(
            repository_sha=SHA,
            role=role,
            count=16,
            offered_rate=100,
            source_shards=2,
            linux_environment=dict(selected_cpus=[0], taskset="/usr/bin/taskset"),
            uid=1000,
            binary_sha256=hashes,
            fixture_sha256=fixture,
            controller_deadline_seconds=120,
            timing="DIAGNOSTIC_ONLY",
            physical_host="NOT_PROVEN",
        )
        write(root, "environment.json", env)
        write(
            root,
            "build-manifest.json",
            dict(source_sha=SHA, build_profile="release", binary_sha256=hashes, build_commands=["fixture"], toolchains={"fixture": True}),
        )
        argv, overrides = command(
            role=role,
            count=16,
            shards=2,
            rate=100,
            binaries=PurePosixPath("/bins"),
            authority=PurePosixPath("/private/tls"),
            lifecycle=PurePosixPath("/private/lifecycle"),
            output=PurePosixPath("/output"),
            bind="192.0.2.1:0" if role == "source" else "192.0.2.2:0",
            endpoint=ready["endpoint"] if role == "source" else None,
        )
        write(root, "command.json", dict(argv=["/usr/bin/taskset", "--cpu-list", "0", *argv], environment_overrides=overrides))
        write(root, "input-readiness.json" if role == "source" else "ready.json", ready)
        samples = [
            dict(pid=123, start_ticks=1, timestamp_ns=100 + i, cpu_ns=10 + i, rss_bytes=1024, affinity=[0], state="S" if i == 0 else "Z")
            for i in range(2)
        ]
        (root / "resources.ndjson").write_text("".join(json.dumps(r) + "\n" for r in samples))
        write(root, "pid.json", dict(pid=123, owns_process_group=True))
        exit_record = dict(exit_code=0, final_sample=samples[-1])
        write(root, "exit.json", exit_record)
        if role == "source":
            rows = [dict(logical_client_id=i, success=True, bytes_received=1024, bytes_transmitted=1024) for i in range(16)]
            rows.append(dict(phase="lifecycle_cleanup", **dict.fromkeys(FIELDS, 0)))
            server = None
        else:
            rows = [dict.fromkeys(FIELDS, 0)]
            server = dict(status="PASS", connections=16, samples=[{} for _ in range(16)])
            write(root, "server-result.json", server)
        (root / ("stdout" if role == "source" else "diagnostics.ndjson")).write_text("".join(json.dumps(r) + "\n" for r in rows))
        result = validate_result(role, 16, rows, server)
        write(
            root,
            "result.json",
            dict(
                status="PASS_FUNCTIONAL_PEER",
                role=role,
                **result,
                process=exit_record,
                timing="DIAGNOSTIC_ONLY",
                paired_active_hold="COORDINATOR_REQUIRED",
                sustainable_capacity="NOT_ESTABLISHED",
                external_hardware="NOT_PROVEN",
            ),
        )
        seal_output(root)
    return roots


def test_pair_rechecks_raw_outcomes_without_claiming_a_held_barrier(tmp_path):
    source, destination = peers(tmp_path)
    result = analyze(source, destination, source_sha=SHA, count=16)
    assert result["status"] == "PASS_FUNCTIONAL_PEER_PAIR"
    assert result["successful_connections"] == 16
    assert result["paired_active_hold"] == "NOT_VERIFIED_BY_THIS_GATE"
    assert result["sustainable_capacity"] == "NOT_ESTABLISHED"


@pytest.mark.parametrize(
    "mutation",
    [
        "fixture",
        "readiness",
        "command",
        "client_id",
        "ownership",
        "summary_count",
        "affinity",
        "cpu",
        "pid_epoch",
        "binary",
        "build",
        "forced",
        "extra_flag",
        "hash_format",
    ],
)
def test_rehashed_inconsistent_pair_is_rejected(tmp_path, mutation):
    source, destination = peers(tmp_path)
    root = destination if mutation == "fixture" else source
    filename = {
        "fixture": "environment.json",
        "readiness": "input-readiness.json",
        "command": "command.json",
        "summary_count": "result.json",
        "build": "build-manifest.json",
        "extra_flag": "command.json",
        "hash_format": "environment.json",
    }.get(mutation)
    if filename:
        value = json.loads((root / filename).read_text())
        if mutation == "fixture":
            value["fixture_sha256"]["certificates"]["source.der"] = "d" * 64
        elif mutation == "readiness":
            value["endpoint"] = "192.0.2.3:4444"
        elif mutation == "command":
            value["argv"][value["argv"].index("--lifecycle-source-shards") + 1] = "1"
        elif mutation == "summary_count":
            value["successful"] = 15
        elif mutation == "build":
            value["source_sha"] = "f" * 40
        elif mutation == "extra_flag":
            value["argv"] += ["--b3-keep-alive-ms", "100"]
        elif mutation == "hash_format":
            value["fixture_sha256"]["certificates"]["ca.der"] = "invalid"
        write(root, filename, value)
    elif mutation in ("client_id", "ownership"):
        rows = [json.loads(x) for x in (root / "stdout").read_text().splitlines()]
        if mutation == "client_id":
            rows[0]["logical_client_id"] = 1
        else:
            rows[-1][FIELDS[0]] = 1
        (root / "stdout").write_text("".join(json.dumps(r) + "\n" for r in rows))
    elif mutation in ("affinity", "cpu", "pid_epoch"):
        rows = [json.loads(x) for x in (root / "resources.ndjson").read_text().splitlines()]
        if mutation == "affinity":
            rows[-1]["affinity"] = [1]
        elif mutation == "cpu":
            rows[-1]["cpu_ns"] = 0
        else:
            rows[-1]["start_ticks"] = 2
        (root / "resources.ndjson").write_text("".join(json.dumps(r) + "\n" for r in rows))
    elif mutation == "binary":
        (root / "executed-binary").write_bytes(b"changed")
    elif mutation == "forced":
        write(root, "forced-cleanup.json", {"valid": False})
    seal_output(root)
    with pytest.raises(ValueError):
        analyze(source, destination, source_sha=SHA, count=16)
