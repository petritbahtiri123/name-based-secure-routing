"""Offline repository analysis planning contracts; no API or credentials."""

import hashlib
import pytest
from scripts.ci import api_repository_plan as m


def entry(path, data, mode="100644"):
    return {
        "path": path,
        "mode": mode,
        "size": len(data),
        "sha": hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest(),
    }


def test_complete_chunks_and_source_free_manifest():
    data = ("α line\n" * 100).encode()
    e = entry("src/a.py", data)
    report = m.plan("a" * 40, [e], lambda _: data, chunk_bytes=64)
    chunks = report["files"][0]["chunks"]
    assert sum(c["bytes"] for c in chunks) == len(data)
    assert chunks[0]["start_byte"] == 0
    assert chunks[-1]["end_byte"] == len(data)
    assert all(c["bytes"] <= 64 for c in chunks)
    assert report["api_calls"] == 0
    assert "α" not in str(report)
    assert report["files"][0]["status"] == "planned"


@pytest.mark.parametrize(
    "path,reason",
    [
        ("evidence/x.json", "archive"),
        ("x.pdf", "binary-media"),
        (".env", "credential-path"),
        ("x.key", "credential-path"),
        ("x.snapshot", "generated"),
        ("Cargo.lock", "generated"),
        ("docs/publication/weekly-evidence/a.md", "archive"),
        ("docs/registries/archive/a.json", "archive"),
        (".superpowers/sdd/old.md", "archive"),
        ("docs/history/old.md", "archive"),
    ],
)
def test_exclusions_never_read(path, reason):
    def forbidden(_):
        raise AssertionError("excluded blob read")

    r = m.plan("a" * 40, [entry(path, b"x")], forbidden)
    assert r["files"][0]["reason"] == reason


@pytest.mark.parametrize(
    "data,reason", [(b"a\0b", "binary-content"), (b"\xff", "non-utf8"), (b"sk-proj-" + b"a" * 40, "possible-credential")]
)
def test_content_rejections(data, reason):
    r = m.plan("a" * 40, [entry("a.py", data)], lambda _: data)
    assert r["files"][0]["reason"] == reason


def test_hash_mismatch_fails_closed():
    with pytest.raises(ValueError):
        m.plan("a" * 40, [entry("a.py", b"x")], lambda _: b"y")


def test_missing_is_not_covered():
    r = m.plan("a" * 40, [entry("a.py", b"x")], lambda _: None)
    assert r["files"][0]["status"] == "unavailable"
    assert r["planned_bytes"] == 0


def test_duplicate_and_unsafe_paths_fail():
    e = entry("a.py", b"x")
    with pytest.raises(ValueError):
        m.plan("a" * 40, [e, e], lambda _: b"x")
    with pytest.raises(ValueError):
        m.plan("a" * 40, [entry("../a.py", b"x")], lambda _: b"x")


def test_nonregular_never_read():
    r = m.plan("a" * 40, [entry("link.py", b"x", "120000")], lambda _: pytest.fail("read link"))
    assert r["files"][0]["reason"] == "non-regular"


def test_empty_has_no_chunks():
    r = m.plan("a" * 40, [entry("a.py", b"")], lambda _: b"")
    assert r["files"][0]["chunks"] == []


@pytest.mark.parametrize("bound", [True, 64.0, 0, 98305])
def test_chunk_bound_exact_integer(bound):
    with pytest.raises(ValueError):
        m.plan("a" * 40, [], lambda _: None, chunk_bytes=bound)


def test_bad_blob_id_rejected_before_reader():
    e = entry("a.py", b"x")
    e["sha"] = "--invalid"
    with pytest.raises(ValueError):
        m.plan("a" * 40, [e], lambda _: pytest.fail("reader called"))


@pytest.mark.parametrize("path,reason", [("private.log", "unsupported-category"), ("Docs/Weekly-Evidence/a.md", "archive")])
def test_positive_categories_and_case_archive(path, reason):
    r = m.plan("a" * 40, [entry(path, b"x")], lambda _: pytest.fail("reader called"))
    assert r["files"][0]["reason"] == reason


def test_known_extensionless_python_entrypoint_is_source():
    data = b'#!/usr/local/bin/python3\nprint("fixture")\n'
    e = entry("tools/demo-lab/container/demo-container-worker", data)
    r = m.plan("a" * 40, [e], lambda _: data)
    assert r["files"][0]["status"] == "planned"
