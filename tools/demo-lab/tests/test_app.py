import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from nbsr_demo_lab.web import Session, check_origin


def test_bootstrap_one_use_and_expiry():
    session = Session(clock=lambda: 10.0)
    secret = session.bootstrap
    token = session.exchange(secret)
    assert token and session.authorized(token)
    assert session.exchange(secret) is None
    late = Session(clock=lambda: 0.0)
    late.clock = lambda: 121.0
    assert late.exchange(late.bootstrap) is None


def test_origin_host_exact():
    assert check_origin('127.0.0.1:1234', 'http://127.0.0.1:1234', 1234)
    assert not check_origin('localhost:1234', 'http://127.0.0.1:1234', 1234)
    assert not check_origin('127.0.0.1:1234', 'https://evil.test', 1234)
    assert not check_origin('127.0.0.1:1234', None, 1234)


def test_token_does_not_authenticate_bootstrap_secret():
    session = Session()
    assert not session.authorized('')
    assert not session.authorized(session.bootstrap)


def test_invalid_scenario_never_dispatches(tmp_path):
    from nbsr_demo_lab.coordinator import Coordinator
    lab = Coordinator(tmp_path, tmp_path / 'state')
    import pytest
    with pytest.raises(ValueError):
        lab.start('../../cmd.exe', 'request-1')
    assert lab.current is None
