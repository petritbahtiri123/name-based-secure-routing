from pathlib import Path
import struct

import pytest


@pytest.mark.parametrize('during_wait', [False, True])
def test_cancelled_packet_client_is_killed_and_reaped_without_extending_deadline(tmp_path, monkeypatch, during_wait):
    import subprocess
    from scripts.performance.linux_b1_capture import LinuxPacketBackend
    events = []
    waiting = False
    class Child:
        pid = 123
        returncode = None
        def wait(self, timeout):
            nonlocal waiting
            if 'kill' in events:
                assert timeout == 5
                self.returncode = -9
                events.append('reap')
                return -9
            assert 0 < timeout <= .1
            waiting = True
            raise subprocess.TimeoutExpired('fixture', timeout)
        def poll(self):
            return self.returncode
        def kill(self):
            events.append('kill')
    monkeypatch.setattr(subprocess, 'Popen', lambda *a, **k: Child())
    def cancelled():
        if not during_wait or waiting:
            raise InterruptedError('SIGTERM fixture')
    backend = LinuxPacketBackend(tmp_path, check_cancelled=cancelled)
    with pytest.raises(InterruptedError, match='SIGTERM'):
        backend.measured_client(['fixture'], cwd=tmp_path, server=None, timeout=600,
                                client_started=lambda pid: events.append('registered'))
    assert events == ['registered', 'kill', 'reap']


def test_cancelled_capture_readiness_still_stops_and_reaps_dumpcap(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from scripts.performance.linux_b1_capture import LinuxPacketObserver
    events = []
    class Child:
        returncode = 0
        def send_signal(self, value):
            events.append('stop')
        def wait(self, timeout):
            events.append('reap')
            return 0
    monkeypatch.setattr('subprocess.Popen', lambda *a, **k: Child())
    monkeypatch.setattr('subprocess.run', lambda *a, **k: SimpleNamespace(returncode=0, stdout=''))
    def cancelled():
        raise InterruptedError('SIGTERM fixture')
    observer = LinuxPacketObserver('dumpcap', 'tshark', 'lo', check_cancelled=cancelled)
    with pytest.raises(InterruptedError, match='SIGTERM'):
        with observer.capture('127.0.0.1:1234', tmp_path):
            pytest.fail('cancelled capture cannot run workload')
    assert events == ['stop', 'reap']
    assert observer.report['valid'] is False


def test_packet_polling_keeps_original_total_timeout(tmp_path, monkeypatch):
    import subprocess
    from scripts.performance import linux_b1_capture as capture
    events = []
    class Child:
        pid = 123
        def poll(self):
            return None
        def kill(self):
            events.append('kill')
        def wait(self, timeout):
            assert timeout == 5  # Cleanup only: the original 600-second bound already expired.
            events.append('reap')
    ticks = iter([0, 601])
    monkeypatch.setattr(capture.time, 'monotonic', lambda: next(ticks, 601))
    monkeypatch.setattr(capture.subprocess, 'Popen', lambda *a, **k: Child())
    with pytest.raises(subprocess.TimeoutExpired) as error:
        capture.LinuxPacketBackend(tmp_path).measured_client(['fixture'], cwd=tmp_path,
            server=None, timeout=600, client_started=lambda _: None)
    assert error.value.timeout == 600
    assert events == ['kill', 'reap']


def test_ethernet_probe_requires_explicit_encapsulation_and_exact_token():
    from scripts.analyze_b1_v2_capture import probe_frames_from_pcapng

    def block(kind, body):
        size = 12 + len(body)
        return struct.pack('<II', kind, size) + body + struct.pack('<I', size)

    probe = dict(source_port=4000, destination_port=4001, token_hex='ab' * 32)
    header = block(0x0A0D0D0A, struct.pack('<IHHq', 0x1A2B3C4D, 1, 0, -1))
    interface = block(1, struct.pack('<HHI', 1, 0, 65535))
    ip = bytes.fromhex('4500003c00000000401100007f0000017f000001')
    frame = b'\0' * 12 + b'\x08\x00' + ip + struct.pack('!HHHH', 4000, 4001, 40, 0) + bytes.fromhex(probe['token_hex'])
    packet = block(6, struct.pack('<IIIII', 0, 0, 0, len(frame), len(frame)) + frame + b'\0\0')
    capture = header + interface + packet
    assert probe_frames_from_pcapng(capture, probe, expected_linktype=1) == {1: probe['token_hex']}
    with pytest.raises(ValueError):
        probe_frames_from_pcapng(capture, probe)  # Windows default stays strict NULL.
    with pytest.raises(ValueError, match='token'):
        probe_frames_from_pcapng(capture, probe | {'token_hex': 'cd' * 32}, expected_linktype=1)
    with pytest.raises(ValueError, match='Ethernet'):
        probe_frames_from_pcapng(capture.replace(b'\x08\x00' + ip, b'\x81\x00' + ip), probe, expected_linktype=1)


def proc_fixture(root, *, start=99, inode=12345, address='0100007F', duplicate=False):
    base = root / '123'
    (base / 'fd').mkdir(parents=True)
    (base / 'net').mkdir()
    (base / 'fd/3').touch()
    fields = ['S'] + ['0'] * 49
    fields[19] = str(start)
    (base / 'stat').write_text('123 (test peer) ' + ' '.join(fields))
    row = f' 1: {address}:1388 00000000:0000 07 00000000:00000000 00:00000000 00000000 65532 0 {inode} 2 0 0\n'
    (base / 'net/udp').write_text('sl local_address rem_address st tx_queue rx_queue tr tm->when retrnsmt uid timeout inode\n' + row * (2 if duplicate else 1))


@pytest.mark.parametrize('change,expected', [({}, 12345), ({'start': 100}, None),
    ({'inode': 54321}, None), ({'address': '0200007F'}, None), ({'duplicate': True}, None),
    ({'address': '00000000'}, 12345)])
def test_udp_ownership_requires_pid_identity_and_matching_socket_inode(tmp_path, monkeypatch, change, expected):
    from scripts.performance.linux_b1_capture import udp_owned_by_pid
    proc_fixture(tmp_path, **change)
    monkeypatch.setattr('os.readlink', lambda path: 'socket:[12345]')
    assert udp_owned_by_pid(('127.0.0.1', 5000), 123, 99, proc_root=tmp_path) == expected


def test_missing_process_does_not_authorize_udp(tmp_path):
    from scripts.performance.linux_b1_capture import udp_owned_by_pid
    assert udp_owned_by_pid(('127.0.0.1', 5000), 123, 99, proc_root=tmp_path) is None


def test_linux_capture_requires_exact_lo_ethernet_metadata():
    from scripts.performance.linux_b1_capture import LinuxPacketObserver
    observer = LinuxPacketObserver(Path('/usr/bin/dumpcap'), Path('/usr/bin/tshark'), 'lo')
    metadata = 'Number of interfaces in file: 1\nName = lo\nEncapsulation = Ethernet\n'
    observer.validate_capture_metadata(metadata)
    observer.validate_capture_metadata(metadata.replace('Ethernet', 'Ethernet (1 - ether)'))
    for invalid in (metadata.replace('Name = lo', 'Name = eth0'), metadata.replace(': 1', ': 2'),
                    metadata.replace('Ethernet', 'Linux cooked-mode capture v2')):
        with pytest.raises(ValueError):
            observer.validate_capture_metadata(invalid)


def test_linux_capture_has_bounded_observer_buffer_without_changing_filter_or_workload(tmp_path):
    from scripts.performance.linux_b1_capture import LinuxPacketObserver
    observer = LinuxPacketObserver(Path('/usr/bin/dumpcap'), Path('/usr/bin/tshark'), 'lo')
    observer.probe = dict(source_port=4000, destination_port=4001)
    command = observer.capture_command(5000, tmp_path / 'capture.pcapng')
    assert command[command.index('-B') + 1] == '64'
    assert command[command.index('-s') + 1] == '0'
    assert command[command.index('-a') + 1] == 'filesize:2097152'
    assert command[command.index('-f') + 1] == observer.capture_filter(5000)


def test_terminal_probe_is_required_and_excluded_from_packet_totals():
    from scripts.analyze_b1_v2_capture import account_packets
    def packet(n, source, dest):
        return {'frame.number': str(n), 'frame.len': '74', 'frame.cap_len': '74',
            'ip.len': '60', 'ip.hdr_len': '20', 'udp.length': '40',
            'ip.src': '127.0.0.1', 'ip.dst': '127.0.0.1', 'ip.flags.mf': '0',
            'ip.frag_offset': '0', 'udp.srcport': str(source), 'udp.dstport': str(dest)}
    probe = dict(source_port=4000, destination_port=4001, token_hex='ab' * 32,
        terminal_token_hex='cd' * 32, observed_frame_numbers=[1], terminal_observed_frame_numbers=[3])
    rows = [packet(1, 4000, 4001), packet(2, 5000, 5001), packet(3, 4000, 4001)]
    result = account_packets(rows, server_port=5001, captured_packets=3,
        readiness_probe=probe, probe_payloads={1: 'ab' * 32, 3: 'cd' * 32})
    assert result['packet_count'] == 1 and result['readiness_probe_packets'] == 2
    with pytest.raises(ValueError, match='terminal'):
        account_packets(rows, server_port=5001, captured_packets=3,
            readiness_probe=probe | {'terminal_observed_frame_numbers': []},
            probe_payloads={1: 'ab' * 32, 3: 'cd' * 32})


def test_packet_pairs_preserve_negative_deltas_and_refuse_missing_or_invalid_runs():
    from scripts.performance.linux_b1_capture import analyze_packet_pairs
    rows = []
    for repeat in range(1, 6):
        for mode in ('direct', 'nbsr'):
            total = 1100 if mode == 'direct' else 1000
            rows.append(dict(path=mode, repeat=repeat, payload_bytes=1024, streams=1,
                operations_per_stream=1, completed_operations=1, application_bytes=2048,
                errors=0, timeouts=0, packet_observer=dict(valid=True,
                    packet_accounting=dict(packet_count=10, ip_bytes=total, udp_bytes=total-200,
                        udp_payload_bytes=total-280, captured_frame_bytes=total+140))))
    summary = analyze_packet_pairs(rows, repeats=5)
    assert summary['cells'][0]['metrics']['ip_bytes']['delta_median'] == -100
    assert summary['performance_capacity'] == 'NOT_PROVEN'
    with pytest.raises(ValueError):
        analyze_packet_pairs(rows[:-1], repeats=5)
    rows[-1]['errors'] = 1
    with pytest.raises(ValueError):
        analyze_packet_pairs(rows, repeats=5)


def test_terminal_marker_failure_still_stops_capture(monkeypatch, tmp_path):
    from types import SimpleNamespace
    from scripts.performance.external_packet_capture import ExternalCapture
    events = []
    class Process:
        returncode = 0
        def send_signal(self, value):
            events.append('stop')
        def wait(self, timeout):
            events.append('join')
    class Observer(ExternalCapture):
        def process_options(self):
            return {}
        def stop_signal(self):
            return 2
        def wait_capture_ready(self, *args):
            (tmp_path / 'loopback.pcapng').touch()
        def finish_capture(self, *args):
            raise TimeoutError('terminal fixture failure')
    monkeypatch.setattr('subprocess.Popen', lambda *a, **k: Process())
    monkeypatch.setattr('subprocess.run', lambda *a, **k: SimpleNamespace(returncode=0, stdout=''))
    observer = Observer('dumpcap', 'tshark', 'lo')
    with pytest.raises(TimeoutError, match='terminal'):
        with observer.capture('127.0.0.1:1234', tmp_path):
            pass
    assert events == ['stop', 'join']
    assert observer.report['valid'] is False
