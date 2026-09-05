from scripts.analyze_b4b_task4l_etw import network_flows


def event(kind, stamp, pid, size, remote, local):
    return [kind, str(stamp), f"peer.exe ({pid})", str(size), "127.000.000.001", str(remote), "127.000.000.001", str(local)]


def test_tcpip_receive_does_not_claim_socket_delivery_or_retransmission():
    rows = [event("UdpSend", 10, 1, 1200, 4000, 5000),
            event("UdpRecv", 11, 2, 1200, 4000, 5000),
            event("UdpSend", 1000010, 1, 1200, 4000, 5000),
            event("UdpSend", 1000100, 2, 1200, 5000, 4000)]
    result = network_flows(rows, 1, 2, 4000)
    assert result[0]["first_tcpip_receive_delay_us"] == 1
    assert result[0]["first_reply_delay_us"] == 1000090
    assert result[0]["socket_delivery"] == "NOT MEASURED"
    assert result[0]["quic_retransmission"] == "NOT ESTABLISHED"


def test_unmatched_reply_remains_unknown_and_unrelated_flow_is_excluded():
    result = network_flows([event("UdpSend", 10, 1, 1200, 4000, 5000),
                            event("UdpSend", 11, 3, 1200, 4000, 5001)], 1, 2, 4000)
    assert len(result) == 1
    assert result[0]["first_reply_delay_us"] is None
    assert result[0]["first_tcpip_receive_delay_us"] is None


def test_next_capture_filters_to_socket_identity_and_drop_events():
    from pathlib import Path
    import xml.etree.ElementTree as ET

    root = ET.parse(Path(__file__).parents[2] / "scripts/performance/task4l-afd.wprp").getroot()
    assert root.findall(".//SystemProvider") == []
    provider = root.find(".//EventProvider")
    # WPR must receive the registered GUID, not merely a display name that
    # profile enumeration can print without resolving a capture provider.
    assert provider.attrib["Name"].lower() == "e53c6823-7bb8-44bb-90dc-3f86090d48a6"
    assert provider.attrib.get("NonPagedMemory") == "true"
    assert provider.attrib.get("Stack", "false") == "false"
    assert {int(e.attrib["Value"]) for e in provider.findall("EventFilters/EventId")} == {1000, 1030, 1033}


def test_gap_cpu_is_clipped_to_observed_interval():
    from scripts.analyze_b4b_task4l_etw import gap_progress

    rows = [
        ["CSwitch", "5", "peer.exe (2)", "20", "", "", "", "", "Idle (0)", "0"],
        ["CSwitch", "25", "Idle (0)", "0", "", "", "", "", "peer.exe (2)", "20"],
        event("UdpSend", 15, 2, 1200, 5000, 4000),
    ]
    result = gap_progress(rows, 2, 10, 20)
    assert result["matched_cpu_us_by_tid"] == {20: 10}
    assert result["udp_sends"] == 1
