from scripts.analyze_b4b_task4l_afd import map_drops


def event(kind, data, stamp="2026-09-05T13:00:01Z", pid=999):
    return {"id": kind, "utc": stamp, "pid": pid,
            "data": {"Process": "p", "Endpoint": "e", **data}}


def test_socket_owner_and_bound_port_determine_role_not_execution_pid():
    rows = [event(1000, {"EnterExit": "0", "ProcessId": "0xa"}),
            event(1030, {"EnterExit": "1", "Status": "0", "Address": "02000FA07F000001"}),
            event(1033, {"Reason": "2", "BufferLength": "1200", "Address": "020013887F000001"})]
    cells = [{"start": 1788613200, "end": 1788613202,
              "admission_port": 4000, "established_port": 4001}]
    result = map_drops(rows, cells)
    assert result["cells"][0]["drops"] == {"admission_destination": 1}
    assert result["cells"][0]["owner_pids"] == [10]
    assert result["unmatched_window_drops"] == 0


def test_reused_endpoint_does_not_inherit_previous_bind():
    rows = [event(1030, {"EnterExit": "1", "Status": "0", "Address": "02000FA07F000001"}),
            event(1000, {"EnterExit": "0", "ProcessId": "0xb"}),
            event(1033, {"Reason": "2", "BufferLength": "35", "Address": "020013887F000001"})]
    result = map_drops(rows, [{"start": 1788613200, "end": 1788613202,
                             "admission_port": 4000, "established_port": 4001}])
    assert result["cells"][0]["drops"] == {"other_or_unmapped": 1}


def test_outside_run_is_retained_and_failed_bind_not_accepted():
    rows = [event(1030, {"EnterExit": "1", "Status": "1", "Address": "02000FA07F000001"}),
            event(1033, {"Reason": "3", "BufferLength": "35", "Address": "020013887F000001"})]
    assert map_drops(rows, [])['unmatched_window_drops'] == 1
