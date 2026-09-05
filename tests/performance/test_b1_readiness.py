from pathlib import Path
import struct
from types import SimpleNamespace

import pytest

from scripts.analyze_b1_v2_capture import account_packets
from scripts.run_b1_v2_capture import PacketObserver
from scripts.performance.external_packet_capture import ExternalCapture


def packet(frame, source, destination, size=32):
    return {"frame.number": str(frame), "frame.len": str(size + 32),
            "frame.cap_len": str(size + 32), "ip.len": str(size + 28), "ip.hdr_len": "20",
            "ip.src": "127.0.0.1", "ip.dst": "127.0.0.1", "udp.srcport": str(source),
            "udp.dstport": str(destination), "udp.length": str(size + 8),
            "ip.flags.mf": "False", "ip.frag_offset": "0"}


def probe():
    return {"source_port": 4000, "destination_port": 4001, "token_hex": "ab" * 32,
            "observed_frame_numbers": [1]}


def test_probe_is_exactly_excluded_after_full_inventory_reconciliation():
    rows = [packet(1, 4000, 4001), packet(2, 5000, 5001, 100)]
    result = account_packets(rows, server_port=5001, captured_packets=2,
                             readiness_probe=probe(), probe_payloads={1: "ab" * 32})
    assert result["packet_count"] == 1
    assert result["capture_inventory_packets"] == 2
    assert result["readiness_probe_packets"] == 1
    assert result["udp_payload_bytes"] == 100
    assert result["captured_frame_bytes"] == 132


@pytest.mark.parametrize("payloads", [{1: "cd" * 32}, {}, {1: "ab" * 32, 2: "ab" * 32}])
def test_wrong_missing_or_extra_probe_evidence_rejects(payloads):
    with pytest.raises(ValueError, match="probe"):
        account_packets([packet(1, 4000, 4001), packet(2, 5000, 5001)],
                        server_port=5001, captured_packets=2,
                        readiness_probe=probe(), probe_payloads=payloads)


def test_probe_cannot_replace_missing_workload_or_hidden_inventory():
    with pytest.raises(ValueError):
        account_packets([packet(1, 4000, 4001)], server_port=5001, captured_packets=1,
                        readiness_probe=probe(), probe_payloads={1: "ab" * 32})
    with pytest.raises(ValueError, match="inventory"):
        account_packets([packet(1, 4000, 4001), packet(2, 5000, 5001)],
                        server_port=5001, captured_packets=3,
                        readiness_probe=probe(), probe_payloads={1: "ab" * 32})


def test_readiness_does_not_accept_live_dumpcap_without_observed_marker(monkeypatch, tmp_path):
    observer = PacketObserver(Path("dumpcap"), Path("tshark"))
    observer.probe = probe()
    observer.probe.pop("observed_frame_numbers")
    attempts = []
    monkeypatch.setattr(observer, "_send_probe", lambda: attempts.append("sent"), raising=False)
    monkeypatch.setattr(observer, "_read_live_probe_payloads", lambda *args, **kwargs: {}, raising=False)
    clock = iter([0, 0, 0.1, 6])
    monkeypatch.setattr("time.monotonic", lambda: next(clock))
    monkeypatch.setattr("time.sleep", lambda _: None)

    class Process:
        def poll(self):
            return None

    with pytest.raises(TimeoutError, match="readiness"):
        observer.wait_capture_ready(Process(), tmp_path / "capture.pcapng", tmp_path)
    assert attempts


def test_readiness_records_observed_probe_before_return(monkeypatch, tmp_path):
    observer = PacketObserver(Path("dumpcap"), Path("tshark"))
    observer.probe = probe()
    observer.probe.pop("observed_frame_numbers")
    sent = []
    monkeypatch.setattr(observer, "_send_probe", lambda: sent.append(True))
    monkeypatch.setattr(observer, "_read_live_probe_payloads", lambda *a, **k: {7: "ab" * 32})
    observer.wait_capture_ready(SimpleNamespace(poll=lambda: None), tmp_path / "open.pcapng", tmp_path)
    assert sent == [True]
    assert observer.report["readiness"]["observed_frame_numbers"] == [7]
    assert observer.report["readiness"]["status"] == "PASS"
    assert (tmp_path / "capture-readiness.json").is_file()


def test_probe_export_rejects_wrong_token(monkeypatch):
    observer = PacketObserver(Path("dumpcap"), Path("tshark"))
    observer.probe = probe()
    monkeypatch.setattr("scripts.run_b1_v2_capture.subprocess.run",
                        lambda *a, **k: SimpleNamespace(returncode=0, stdout="1\t" + "cd" * 32))
    with pytest.raises(ValueError, match="token"):
        observer._read_probe_payloads(Path("open.pcapng"), timeout=1)


def test_failed_startup_hook_closes_capture_without_yielding(monkeypatch, tmp_path):
    events = []

    class Capture(ExternalCapture):
        def capture_filter(self, server_port):
            return "custom probe filter"

        def wait_capture_ready(self, process, pcap, cell_dir):
            raise TimeoutError("probe not observed")

    class Process:
        returncode = 0

        def __init__(self, command, **kwargs):
            assert command[command.index("-f") + 1] == "custom probe filter"

        def send_signal(self, signal):
            events.append("stop")

        def wait(self, timeout):
            events.append("wait")

    monkeypatch.setattr("scripts.performance.external_packet_capture.subprocess.Popen", Process)
    monkeypatch.setattr("scripts.performance.external_packet_capture.subprocess.run",
                        lambda *a, **k: SimpleNamespace(returncode=0, stdout=""))
    observer = Capture(Path("dumpcap"), Path("tshark"))
    with pytest.raises(TimeoutError, match="probe"):
        with observer.capture("127.0.0.1:5001", tmp_path):
            pytest.fail("workload started without verified readiness")
    assert events == ["stop", "wait"]
    assert observer.report["valid"] is False


def test_live_pcapng_prefix_accepts_complete_probe_before_partial_next_block():
    from scripts.analyze_b1_v2_capture import probe_frames_from_pcapng

    def block(kind, body):
        length = len(body) + 12
        return struct.pack("<II", kind, length) + body + struct.pack("<I", length)

    header = block(0x0A0D0D0A, struct.pack("<IHHq", 0x1A2B3C4D, 1, 0, -1))
    interface = block(1, struct.pack("<HHI", 0, 0, 65535))
    ipv4 = bytes.fromhex("4500003c00000000401100007f0000017f000001")
    payload = bytes.fromhex(probe()["token_hex"])
    frame = struct.pack("<I", 2) + ipv4 + struct.pack("!HHHH", 4000, 4001, 40, 0) + payload
    enhanced = block(6, struct.pack("<IIIII", 0, 0, 0, len(frame), len(frame)) + frame)
    assert probe_frames_from_pcapng(header + interface + enhanced + enhanced[:19], probe()) == {1: payload.hex()}
    assert probe_frames_from_pcapng(header + interface + enhanced[:-1], probe()) == {}
    with pytest.raises(ValueError, match="token"):
        probe_frames_from_pcapng(header + interface + enhanced, {**probe(), "token_hex": "cd" * 32})
