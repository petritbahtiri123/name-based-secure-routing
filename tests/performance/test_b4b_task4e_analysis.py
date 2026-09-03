import importlib
import io


def test_wait_and_ready_are_separate_and_cpu_time_is_not_switch_count():
    module = importlib.import_module("scripts.analyze_b4b_task4e")
    rows = io.StringIO(
        'CSwitch,100,p,9,0,0,0,0,p,7,0,0,Waiting,WrQueue\n'
        'ReadyThread,160,p,9,p,7\n'
        'CSwitch,200,p,7,0,0,0,0,p,9,0,0,Ready,WrPreempted\n'
    )
    result = module.scheduling(rows, {7})[7]
    assert result["switch_out_count"] == 1
    assert result["wait_us"] == 60
    assert result["ready_us"] == 40
    assert result["unresolved_intervals"] == 0


def test_missing_wakeup_does_not_invent_wait_attribution():
    module = importlib.import_module("scripts.analyze_b4b_task4e")
    rows = io.StringIO(
        'CSwitch,100,p,9,0,0,0,0,p,7,0,0,Waiting,Executive\n'
        'CSwitch,200,p,7,0,0,0,0,p,9,0,0,Ready,WrPreempted\n'
    )
    result = module.scheduling(rows, {7})[7]
    assert result["unresolved_intervals"] == 1
    assert result["wait_us"] == 0
    assert result["ready_us"] == 0
