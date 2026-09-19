import signal
import subprocess
from types import SimpleNamespace


def test_capture_ignoring_graceful_and_terminate_is_killed_reaped_and_invalid(tmp_path, monkeypatch):
    from scripts.performance.external_packet_capture import ExternalCapture
    events, opened = [], []
    class Child:
        returncode = None
        def send_signal(self, value):
            events.append(('signal', value))
        def wait(self, timeout):
            events.append(('wait', timeout))
            if 'kill' not in events:
                raise subprocess.TimeoutExpired('capture-fixture', timeout)
            self.returncode = -9
            return -9
        def terminate(self):
            events.append('terminate')
        def kill(self):
            events.append('kill')
    def spawn(*args, **kwargs):
        opened.append(kwargs['stderr'])
        return Child()
    monkeypatch.setattr(subprocess, 'Popen', spawn)
    monkeypatch.setattr(subprocess, 'run', lambda *a, **k: SimpleNamespace(returncode=0, stdout=''))
    observer = ExternalCapture('dumpcap', 'tshark')
    monkeypatch.setattr(observer, 'process_options', dict)
    monkeypatch.setattr(observer, 'stop_signal', lambda: signal.SIGINT)
    monkeypatch.setattr(observer, 'wait_capture_ready', lambda *args: None)
    with observer.capture('127.0.0.1:4000', tmp_path):
        pass
    assert events == [('signal', signal.SIGINT), ('wait', 10), 'terminate', ('wait', 5), 'kill', ('wait', 5)]
    assert observer.report['valid'] is False
    assert observer.report['dumpcap_returncode'] == -9
    assert opened[0].closed


def test_capture_final_reap_failure_still_closes_stderr(tmp_path, monkeypatch):
    from scripts.performance.external_packet_capture import ExternalCapture
    import pytest
    opened = []
    class Child:
        def send_signal(self, value):
            pass
        def wait(self, timeout):
            raise subprocess.TimeoutExpired('fixture', timeout)
        def terminate(self):
            pass
        def kill(self):
            pass
    def spawn(*args, **kwargs):
        opened.append(kwargs['stderr'])
        return Child()
    observer = ExternalCapture('dumpcap', 'tshark')
    monkeypatch.setattr(subprocess, 'Popen', spawn)
    monkeypatch.setattr(observer, 'process_options', dict)
    monkeypatch.setattr(observer, 'stop_signal', lambda: signal.SIGINT)
    monkeypatch.setattr(observer, 'wait_capture_ready', lambda *args: None)
    with pytest.raises(subprocess.TimeoutExpired):
        with observer.capture('127.0.0.1:4000', tmp_path):
            pass
    assert opened[0].closed
