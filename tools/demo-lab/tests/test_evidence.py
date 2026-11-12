import hashlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from nbsr_demo_lab.evidence import BODY, EXPECTED_TESTS, verify, write_receipt, write_attempt


def make(tmp_path, scenario="allowed_service_a", cleanup="CLEAN", output=None, execution=None, **changes):
    provenance = dict(source_commit="a" * 40, source_hashes={"src/main.go": "b" * 64},
                      binary_hashes={"worker": "c" * 64}, platform="windows",
                      toolchain={"go": "go1.24.1"})
    if execution is not None:
        provenance["platform"] = execution["execution_platform"]
    live = scenario == "allowed_service_a"
    result = dict(exit_code=0, reason="completed", cancelled=False, timeout=False,
                  expected_tests=[] if live else [EXPECTED_TESTS[scenario]],
                  regression_kind=None if live else "fixture_regression")
    result.update(changes)
    artifacts = {"application.json": json.dumps({"body": BODY}),
                 "destination.json": json.dumps({"status": "PASS", "backend_requests": 1})} if live else {
                     "test-output.txt": output or f"=== RUN   {EXPECTED_TESTS[scenario]}\n--- PASS: {EXPECTED_TESTS[scenario]} (0.01s)\nPASS\n"}
    return write_receipt(tmp_path, scenario, provenance, result, cleanup, artifacts, execution=execution)


def rewrite(tmp_path, edit):
    path = tmp_path / "receipt.json"
    receipt = json.loads(path.read_text())
    edit(receipt)
    path.write_text(json.dumps(receipt))


def test_live_pass(tmp_path):
    make(tmp_path)
    assert verify(tmp_path)["outcome"] == "PASS"


@pytest.mark.parametrize("scenario", EXPECTED_TESTS)
def test_fixed_regressions(tmp_path, scenario):
    make(tmp_path, scenario)
    assert verify(tmp_path)["outcome"] == "PASS"


def test_go_json(tmp_path):
    name = EXPECTED_TESTS["unknown_service"]
    output = "\n".join(json.dumps(event) for event in [
        {"Action": "run", "Test": name}, {"Action": "pass", "Test": name}, {"Action": "pass"}])
    make(tmp_path, "unknown_service", output=output)
    assert verify(tmp_path)["outcome"] == "PASS"


@pytest.mark.parametrize("output", ["PASS\n", "=== RUN   Other\n--- PASS: Other (0.01s)\nPASS\n",
                                      "=== RUN   {name}\n--- SKIP: {name} (0.01s)\nPASS\n",
                                      "=== RUN   {name}\n--- PASS: {name} (0.01s)\n--- FAIL: Other (0.01s)\nPASS\n"])
def test_missing_or_skipped_tests(tmp_path, output):
    make(tmp_path, "unknown_service", output=output.format(name=EXPECTED_TESTS["unknown_service"]))
    assert verify(tmp_path)["outcome"] != "PASS"


@pytest.mark.parametrize("change", ["modified", "missing", "forged_body", "extra", "duplicate", "nan"])
def test_tampering(tmp_path, change):
    make(tmp_path)
    path = tmp_path / "application.json"
    if change == "missing":
        path.unlink()
    elif change in ("modified", "forged_body"):
        path.write_text('{"body":"wrong"}')
        if change == "forged_body":
            rewrite(tmp_path, lambda r: r["artifacts"].update({"application.json": hashlib.sha256(path.read_bytes()).hexdigest()}))
    elif change == "extra":
        rewrite(tmp_path, lambda r: r.update(outcome="PASS"))
    else:
        receipt = tmp_path / "receipt.json"
        receipt.write_text(receipt.read_text().replace('"schema_version": 1',
                           '"schema_version": 1, "schema_version": 1' if change == "duplicate" else '"schema_version": NaN'))
    assert verify(tmp_path)["outcome"] != "PASS"


@pytest.mark.parametrize("cleanup", ["UNCONFIRMED", "FAILED"])
def test_cleanup_independent(tmp_path, cleanup):
    make(tmp_path, cleanup=cleanup)
    result = verify(tmp_path)
    assert result["scenario_outcome"] == "PASS"
    assert result["outcome"] != "PASS"


@pytest.mark.parametrize("changes", [{"exit_code": 1}, {"cancelled": True}, {"timeout": True}, {"reason": "output_limit"}, {"reason": "source_or_binary_changed"}])
def test_crash_is_failure(tmp_path, changes):
    make(tmp_path, "unknown_service", **changes)
    assert verify(tmp_path)["outcome"] == "FAIL"


def test_symlink(tmp_path):
    make(tmp_path)
    path = tmp_path / "application.json"
    target = tmp_path / "other.json"
    path.rename(target)
    try:
        path.symlink_to(target)
    except OSError:
        pytest.skip("host does not permit symlink creation")
    assert verify(tmp_path)["outcome"] != "PASS"


def test_traversal(tmp_path):
    make(tmp_path)
    rewrite(tmp_path, lambda r: r["artifacts"].update({"../outside": "a" * 64}))
    assert verify(tmp_path)["outcome"] != "PASS"


def test_no_overwrite(tmp_path):
    make(tmp_path)
    before = (tmp_path / "receipt.json").read_bytes()
    with pytest.raises(ValueError):
        make(tmp_path)
    assert (tmp_path / "receipt.json").read_bytes() == before


def test_nested_skip_rejected(tmp_path):
    name = EXPECTED_TESTS["unknown_service"]
    make(tmp_path, "unknown_service", output=f"=== RUN   {name}\n    --- SKIP: {name}/child (0.01s)\n--- PASS: {name} (0.01s)\nPASS\n")
    assert verify(tmp_path)["outcome"] != "PASS"


def test_pass_before_run_rejected(tmp_path):
    name = EXPECTED_TESTS["unknown_service"]
    make(tmp_path, "unknown_service", output=f"--- PASS: {name} (0.01s)\n=== RUN   {name}\nPASS\n")
    assert verify(tmp_path)["outcome"] != "PASS"


def test_private_source_path_rejected(tmp_path):
    make(tmp_path)
    rewrite(tmp_path, lambda r: r["provenance"]["source_hashes"].update({"C:/private/source.go": "f" * 64}))
    assert verify(tmp_path)["outcome"] != "PASS"


def execution_identity(host="Darwin-arm64", platform="Linux-aarch64"):
    return dict(mode="mac_host_linux_container", host_platform=host, execution_platform=platform,
                image_id="sha256:" + "a" * 64, container_id="b" * 64)


@pytest.mark.parametrize("host,platform", [("Darwin-arm64", "Linux-aarch64"), ("Darwin-x86_64", "Linux-x86_64")])
def test_v2_native_container_receipt(tmp_path, host, platform):
    receipt = make(tmp_path, execution=execution_identity(host, platform))
    assert receipt["schema_version"] == 2
    checked = verify(tmp_path)
    assert checked["valid"] and checked["outcome"] == "PASS"
    assert checked["receipt"]["execution"] == execution_identity(host, platform)


def test_v1_default_unchanged(tmp_path):
    receipt = make(tmp_path)
    assert receipt["schema_version"] == 1 and "execution" not in receipt
    assert verify(tmp_path)["outcome"] == "PASS"


@pytest.mark.parametrize("field,value", [
    ("mode", "native_mac"), ("host_platform", "Linux-aarch64"),
    ("host_platform", "Darwin-x86_64"), ("execution_platform", "Linux-x86_64"),
    ("execution_platform", "Darwin-arm64"), ("image_id", "demo:latest"),
    ("image_id", "sha256:" + "a" * 63), ("container_id", "abc123"),
    ("container_id", "b" * 63 + "G"), ("container_id", None),
])
def test_v2_spoofed_identity_rejected(tmp_path, field, value):
    make(tmp_path, execution=execution_identity())
    rewrite(tmp_path, lambda r: r["execution"].update({field: value}))
    assert not verify(tmp_path)["valid"]


@pytest.mark.parametrize("field", ["mode", "host_platform", "execution_platform", "image_id", "container_id"])
def test_v2_missing_identity_rejected(tmp_path, field):
    make(tmp_path, execution=execution_identity())
    rewrite(tmp_path, lambda r: r["execution"].pop(field))
    assert verify(tmp_path)["outcome"] != "PASS"


@pytest.mark.parametrize("mutation", [
    lambda r: r.pop("execution"),
    lambda r: r["execution"].update(extra="forged"),
    lambda r: r["provenance"].update(platform="Darwin-arm64"),
    lambda r: r.update(schema_version=1),
    lambda r: r.update(schema_version=3),
    lambda r: r.update(schema_version=True),
    lambda r: r.update(schema_version=2.0),
])
def test_v2_schema_mismatch_rejected(tmp_path, mutation):
    make(tmp_path, execution=execution_identity())
    rewrite(tmp_path, mutation)
    assert verify(tmp_path)["outcome"] != "PASS"


@pytest.mark.parametrize("cleanup", ["UNCONFIRMED", "FAILED"])
def test_v2_cleanup_stays_independent(tmp_path, cleanup):
    make(tmp_path, execution=execution_identity(), cleanup=cleanup)
    assert verify(tmp_path)["outcome"] != "PASS"


def test_v2_writer_rejects_emulation_before_writing(tmp_path):
    with pytest.raises(ValueError, match="non-native"):
        make(tmp_path, execution=execution_identity("Darwin-arm64", "Linux-x86_64"))
    assert not (tmp_path / "receipt.json").exists()


def attempt_record(**changes):
    record = dict(schema="nbsr-demo-attempt-v1", run_id="demo-" + "a" * 32,
                  source_commit="b" * 40, expected_source_hashes={"src/main.go": "c" * 64},
                  host_platform="Darwin-arm64", image_id="sha256:" + "d" * 64,
                  container_id=None, exit_code=None, reason="inner receipt unavailable", cleanup="CLEAN")
    record.update(changes)
    return record


@pytest.mark.parametrize("exit_code,cleanup,outcome", [(None, "CLEAN", "INCOMPLETE"),
    (0, "CLEAN", "INCOMPLETE"), (0, "UNCONFIRMED", "INCOMPLETE"),
    (1, "CLEAN", "FAIL"), (None, "FAILED", "FAIL")])
def test_missing_inner_attempt_never_passes(tmp_path, exit_code, cleanup, outcome):
    record = attempt_record(exit_code=exit_code, cleanup=cleanup)
    assert write_attempt(tmp_path, record) == record
    checked = verify(tmp_path)
    assert checked["valid"] and checked["outcome"] == outcome
    assert checked["scenario_outcome"] == "INCOMPLETE"
    assert checked["cleanup"] == cleanup and checked["receipt"] == record
    assert checked["errors"]


@pytest.mark.parametrize("changes", [
    {"schema": "nbsr-demo-attempt-v2"}, {"run_id": "../unsafe"}, {"source_commit": "a"},
    {"expected_source_hashes": {}}, {"expected_source_hashes": {"../secret": "a" * 64}},
    {"expected_source_hashes": {"C:/private/a.go": "a" * 64}},
    {"expected_source_hashes": {"src/a.go": "wrong"}}, {"host_platform": "Linux-aarch64"},
    {"image_id": "demo:latest"}, {"container_id": "short"}, {"exit_code": True},
    {"reason": ""}, {"cleanup": "unknown"}, {"outcome": "PASS"},
])
def test_malformed_attempt_rejected(tmp_path, changes):
    record = attempt_record(**changes)
    with pytest.raises(ValueError):
        write_attempt(tmp_path, record)
    (tmp_path / "attempt.json").write_text(json.dumps(record))
    checked = verify(tmp_path)
    assert not checked["valid"] and checked["outcome"] != "PASS"


@pytest.mark.parametrize("field", list(attempt_record()))
def test_attempt_missing_field(tmp_path, field):
    record = attempt_record()
    record.pop(field)
    (tmp_path / "attempt.json").write_text(json.dumps(record))
    assert not verify(tmp_path)["valid"]


def test_attempt_cannot_mask_existing_invalid_receipt(tmp_path):
    write_attempt(tmp_path, attempt_record())
    (tmp_path / "receipt.json").write_text("{}")
    assert not verify(tmp_path)["valid"]


def test_attempt_exclusive_write(tmp_path):
    write_attempt(tmp_path, attempt_record(container_id="f" * 64))
    before = (tmp_path / "attempt.json").read_bytes()
    with pytest.raises(FileExistsError):
        write_attempt(tmp_path, attempt_record())
    assert (tmp_path / "attempt.json").read_bytes() == before
