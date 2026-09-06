from copy import deepcopy

import pytest

from scripts.performance.b3_linux_analysis import analyze_cycles, analyze_scale


def cell(amount=1000, name='r1', cycles=3):
    rows = []
    for role, pid in [('source', 10), ('destination', 20)]:
        for cycle in range(cycles):
            for phase in ('idle', 'active', 'cooldown'):
                memory = amount if phase == 'active' else 100 + cycle
                rows.append(dict(platform='linux', role=role, cycle=cycle, phase=phase,
                    process_count=1, memory_basis='linux_smaps_rollup', private_resident_bytes=memory,
                    rss_bytes=memory + 50, pss_bytes=memory + 30, private_hugetlb_bytes=4,
                    fd_count=3, thread_count=2,
                    processes=[dict(pid=pid, start_ticks=10, private_resident_bytes=memory,
                        rss_bytes=memory + 50, pss_bytes=memory + 30, private_hugetlb_bytes=4,
                        fd_count=3, thread_ids=[pid, pid + 1])]))
    return dict(name=name, kind='streams', cycles=cycles, active_count=16, resource_scope='fixed channels',
                materialized_streams=True, cleanup={'all_zero': True, 'source_cycle_all_zero': True}, samples=rows)


def test_linux_cycle_metrics_are_explicit_not_windows_aliases():
    result = analyze_cycles(cell())
    assert result['roles']['source']['private_resident_slope_bytes_per_cycle'] == 1
    assert result['memory_cause'] == 'INCONCLUSIVE' and result['ownership'] == 'CLEAN'
    assert 'private_slope_bytes_per_cycle' not in result['roles']['source']


@pytest.mark.parametrize('change', ['pid', 'start', 'count', 'platform', 'missing', 'cleanup'])
def test_linux_analysis_rejects_broken_evidence(change):
    value = cell()
    row = value['samples'][-1]
    if change == 'pid':
        row['processes'][0]['pid'] += 1
    elif change == 'start':
        row['processes'][0]['start_ticks'] += 1
    elif change == 'count':
        row['process_count'] = 2
    elif change == 'platform':
        row['platform'] = 'windows'
    elif change == 'missing':
        value['samples'].pop()
    else:
        value['cleanup'].pop('source_cycle_all_zero')
    with pytest.raises(ValueError):
        analyze_cycles(value)


def test_scale_requires_valid_repeats_and_retains_linux_names():
    values = [cell(v, str(i)) for i, v in enumerate((1000, 2000, 3000))]
    result = analyze_scale(values)
    point = result[0]['points'][0]
    assert point['repeats'] == 3 and not point['repeat_gate']
    assert point['active_private_resident_median'] == 2000
    stable = analyze_scale([cell(1000, str(i)) for i in range(3)])
    assert stable[0]['points'][0]['repeat_gate']
    values[0]['cleanup']['all_zero'] = False
    with pytest.raises(ValueError):
        analyze_scale(values)


def test_scale_refuses_mixed_residency_and_duplicate_repeat():
    value = cell()
    other = deepcopy(value)
    with pytest.raises(ValueError):
        analyze_scale([value, other])
    other['name'] = 'r2'
    other['materialized_streams'] = False
    with pytest.raises(ValueError):
        analyze_scale([value, other])
