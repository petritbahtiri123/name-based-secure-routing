import pytest

from scripts.run_b4b_task4m import verified_binaries


def test_modified_baseline_binary_is_rejected(tmp_path):
    for name in ("perf_rust_source.exe", "wp8_interop_server.exe", "perf_direct_peer.exe"):
        (tmp_path / name).write_bytes(b"changed")
    with pytest.raises(ValueError, match="binary hash"):
        verified_binaries(tmp_path, {"nbsr": "wrong", "server": "wrong", "direct": "wrong"})
