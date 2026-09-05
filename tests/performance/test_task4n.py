import os

import pytest

from scripts.run_b4b_task4n import profile_environment


def test_profile_environment_restores_previous_value_even_on_failure(monkeypatch, tmp_path):
    key = "NBSR_PERF_ACCEPT_PUMP_PROFILE"
    monkeypatch.setenv(key, "previous")
    with pytest.raises(RuntimeError):
        with profile_environment(tmp_path / "profile.json"):
            assert os.environ[key] == str(tmp_path / "profile.json")
            raise RuntimeError("failed measurement")
    assert os.environ[key] == "previous"
    with profile_environment(None):
        assert key not in os.environ
    assert os.environ[key] == "previous"
