import pytest

from scripts.analyze_b1_v2_capture import account_packets, capture_drop_counts


def packet():
    return {"frame.len": "132", "frame.cap_len": "132", "ip.len": "128", "ip.hdr_len": "20",
            "ip.src": "127.0.0.1", "ip.dst": "127.0.0.1", "udp.srcport": "1234", "udp.dstport": "5678",
            "udp.length": "108", "ip.flags.mf": "0", "ip.frag_offset": "0"}


def test_measured_layers_are_separate_from_nbsr_delta():
    result = account_packets([packet()], server_port=5678, captured_packets=1)
    assert result["captured_frame_bytes"] == 132
    assert result["ip_bytes"] == 128
    assert result["udp_bytes"] == 108
    assert result["udp_payload_bytes"] == 100
    assert result["physical_ethernet_bytes"] is None
    assert "nbsr_overhead" not in result


def test_tshark_boolean_fragment_flag_is_supported():
    row = {**packet(), "ip.flags.mf": "False"}
    assert account_packets([row], server_port=5678, captured_packets=1)["packet_count"] == 1
    row["ip.flags.mf"] = "True"
    with pytest.raises(ValueError, match="fragmented"):
        account_packets([row], server_port=5678, captured_packets=1)


@pytest.mark.parametrize("field,value", [("frame.cap_len", "130"), ("ip.src", "10.1.2.3"),
                                        ("ip.frag_offset", "1"), ("udp.length", "200")])
def test_truncation_mixed_flow_fragment_or_bad_lengths_reject(field, value):
    row = packet()
    row[field] = value
    with pytest.raises(ValueError):
        account_packets([row], server_port=5678, captured_packets=1)


def test_drop_evidence_must_be_explicit_and_reconcile():
    text = "Packets captured: 265\nPackets received/dropped on interface 'Adapter for loopback traffic capture': 265/0 (pcap:0/dumpcap:0/flushed:0/ps_ifdrop:0) (100.0%)\n"
    assert capture_drop_counts(text)["dropped"] == 0
    with pytest.raises(ValueError):
        capture_drop_counts("Packets captured: 265\n")
    with pytest.raises(ValueError):
        capture_drop_counts(text.replace("pcap:0", "pcap:1"))


def test_hidden_packets_and_multiple_client_flows_reject():
    with pytest.raises(ValueError):
        account_packets([packet()], server_port=5678, captured_packets=2)
    other = {**packet(), "udp.srcport": "4321"}
    with pytest.raises(ValueError):
        account_packets([packet(), other], server_port=5678, captured_packets=2)
