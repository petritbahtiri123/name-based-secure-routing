import copy
import json

import pytest

from scripts.performance import linux_native_lifecycle as native
from scripts.performance.linux_native_lifecycle_coordinator import endpoint_arguments, validate_config
from tests.performance.test_linux_native_lifecycle_coordinator import config


def host():
    return dict(inherited_cpus=[0,1,2,3], selected_cpus=[0], topology=dict(cpus=[
        dict(cpu=i, core=i%2, socket=0, node=0, online=True) for i in range(4)]))


def test_explicit_pool_changes_only_selected_child_cpus():
    original = host()
    assert native.select_cpu_pool(original, 1, None) == original
    selected = native.select_cpu_pool(original, 1, [1])
    assert selected['selected_cpus'] == [1] and selected['requested_cpu_pool'] == [1]
    assert selected['inherited_cpus'] == [0,1,2,3]
    assert original == host()
    assert native.select_cpu_pool(original, 2, [0,1])['selected_cpus'] == [0,1]


@pytest.mark.parametrize('cores,pool', [(1,[True]),(1,[]),(1,[4]),(2,[0,0]),(2,[1,0]),(2,[0,2]),(1,[-1])])
def test_pool_rejects_unavailable_or_false_physical_core_allocation(cores,pool):
    with pytest.raises(ValueError):
        native.select_cpu_pool(host(), cores, pool)


def test_coordinator_forwards_optional_pool_and_preserves_default():
    value = config()
    assert '--cpu-pool' not in endpoint_arguments(value,'source')
    value['destination']['cpu_pool'] = [1]
    assert validate_config(value) == value
    argv = endpoint_arguments(value,'destination')
    assert argv[argv.index('--cpu-pool')+1] == '1'
    invalid = copy.deepcopy(value)
    invalid['destination']['cpu_pool'] = [True]
    with pytest.raises(ValueError):
        validate_config(invalid)


def test_pool_cli_parse_is_bounded_canonical_and_explicit():
    assert native.parse_cpu_pool('0,1') == [0,1]
    for value in ('','1,1','1,0','-1','0-7','true','1,'+'1'*100):
        with pytest.raises(ValueError):
            native.parse_cpu_pool(value)


def test_pool_rejects_cross_numa_pair():
    value = host()
    value['topology']['cpus'][1]['node'] = 1
    with pytest.raises(ValueError, match='NUMA'):
        native.select_cpu_pool(value, 2, [0,1])


def test_independent_pair_gate_rejects_resealed_cpu_request_mismatch(tmp_path):
    from scripts.performance.linux_b5_placement import seal_output
    from scripts.performance.linux_native_lifecycle_pair import analyze
    from tests.performance.test_linux_native_lifecycle_pair import SHA, peers

    source, destination = peers(tmp_path)
    path = source/'environment.json'
    value = json.loads(path.read_text())
    value['linux_environment'].update(host(), requested_cpu_pool=[1])
    path.write_text(json.dumps(value))
    seal_output(source)
    with pytest.raises(ValueError, match='CPU pool mismatch'):
        analyze(source,destination,source_sha=SHA,count=16)
