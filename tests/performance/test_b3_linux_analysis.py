from copy import deepcopy
import hashlib
import json

import pytest

from scripts.performance.b3_linux_analysis import analyze_cycles, analyze_scale
from scripts.performance import b3_linux_analysis as analysis


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


def test_scale_allows_explicit_postclose_source_but_cycles_do_not():
    value = cell(cycles=1)
    value.update(kind='sessions', sessions=2)
    row = next(r for r in value['samples'] if r['role'] == 'source' and r['phase'] == 'cooldown')
    row['memory_state'] = 'UNAVAILABLE_EXPECTED_EXIT'
    for field in ('private_resident_bytes', 'rss_bytes', 'pss_bytes', 'private_hugetlb_bytes', 'fd_count', 'thread_count'):
        row[field] = None
    row['processes'][0] = dict(pid=10, start_ticks=10, state='EXITED', exit_code=0,
        memory_state='UNAVAILABLE_EXPECTED_EXIT')
    assert analyze_scale([value])[0]['points'][0]['active_private_resident_median'] == 1000
    with pytest.raises(ValueError):
        analyze_cycles(value)


def evidence(root, name='r1', **changes):
    root.mkdir()
    names = {'rust': 'perf_rust_source', 'server': 'wp8_interop_server'}
    (root / 'binaries').mkdir()
    hashes = {}
    for role, filename in names.items():
        (root / 'binaries' / filename).write_bytes(role.encode())
        hashes[role] = hashlib.sha256(role.encode()).hexdigest()
    env = dict(platform='linux', source_sha='a' * 40, binary_source_sha='b' * 40,
        binary_sha256=hashes, classification='DIAGNOSTIC_BINARY_SOURCE_MISMATCH', memory_scope='Linux private resident',
        linux_environment=dict(topology={'cpus': [{'cpu': 0, 'core': 0}]}, selected_cpus=[0], inherited_cpus=[0],
            kernel='Linux test', python='3.14', taskset_version='2', lscpu_version='2', cgroup_observed={'cpu.max': '1'}))
    env.update(changes)
    (root / 'environment.json').write_text(json.dumps(env))
    build = dict(source_sha=env['binary_source_sha'], build_profile='release', build_commands=['known'],
                 toolchains={'rust': 'known'}, binary_sha256={names[r]: h for r, h in hashes.items()})
    (root / 'build-manifest.json').write_text(json.dumps(build))
    (root / 'records.json').write_text(json.dumps([cell(name=name, cycles=1)]))
    for filename in ['run_b3_v2.py', 'run_b3_session_lifecycle.py', 'performance/b3_linux.py',
                     'performance/b3_linux_analysis.py', 'performance/linux_resources.py', 'performance/linux_loopback.py']:
        path = root / 'source' / 'scripts' / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('retained controller source\n')
    index(root)


def index(root):
    (root / 'checksums.sha256').write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest() + '  ' +
        p.relative_to(root).as_posix() + '\n' for p in sorted(root.rglob('*')) if p.is_file() and p.name != 'checksums.sha256'))


def test_pool_preserves_diagnostic_classification_and_hash_provenance(tmp_path):
    root = tmp_path / 'r1'
    evidence(root)
    result = analysis.analyze_roots([root])
    assert result['classification'] == 'DIAGNOSTIC_BINARY_SOURCE_MISMATCH'
    assert result['inputs'][0]['checksums_sha256'] == hashlib.sha256((root / 'checksums.sha256').read_bytes()).hexdigest()
    assert result['inputs'][0]['binary_source_sha'] == 'b' * 40


@pytest.mark.parametrize('change', ['controller_sha', 'binary_sha', 'placement', 'topology', 'memory', 'source_bytes', 'raw_tamper'])
def test_pool_rejects_incompatible_or_unverified_inputs(tmp_path, change):
    a, b = tmp_path / 'a', tmp_path / 'b'
    evidence(a, 'r1')
    evidence(b, 'r2')
    env = json.loads((b / 'environment.json').read_text())
    if change == 'controller_sha':
        env['source_sha'] = 'c' * 40
    elif change == 'binary_sha':
        env['binary_source_sha'] = 'c' * 40
    elif change == 'placement':
        env['linux_environment']['selected_cpus'] = [1]
    elif change == 'topology':
        env['linux_environment']['topology']['cpus'][0]['core'] = 1
    elif change == 'memory':
        env['memory_scope'] = 'Windows private commit'
    elif change == 'source_bytes':
        (b / 'source/scripts/run_b3_v2.py').write_text('changed')
    else:
        (b / 'records.json').write_text('[]')
    (b / 'environment.json').write_text(json.dumps(env))
    if change != 'raw_tamper':
        index(b)
    with pytest.raises(ValueError):
        analysis.analyze_roots([a, b])
