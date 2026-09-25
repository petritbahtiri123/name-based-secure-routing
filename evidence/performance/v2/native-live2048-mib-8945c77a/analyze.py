"""Replay fixed observer-off diagnostic including every failed trial."""

import json
from collections import Counter
from pathlib import Path
import sys

sys.path.insert(0, str(Path.cwd()))
from scripts.performance.linux_native_lifecycle_gate import check_endpoint
from scripts.performance.linux_native_lifecycle_pair import analyze, check_peer
from scripts.performance.linux_native_pair import verify_index
from scripts.performance.post_close_cleanup import FIELDS
from scripts.performance.linux_loopback import digest

def verified_individual_peer(peer, role, sha, count):
    return check_peer(peer, role, sha, count, memory_observer=False, bundle_mode='live-bundles')['outcome']


root = Path(sys.argv[1])
verify_index(root)
records = json.loads((root / 'records.json').read_bytes())
assert [r['repeat'] for r in records] == [1, 2, 3], 'cohort identity: expected three attempted trials'
assert all(r['status'] in ('PASS_FUNCTIONAL', 'FAIL_RETAINED') for r in records)
counts = (2048,)
assert {r['count'] for r in records} == set(counts)
assert len({r['label'] for r in records}) == len(records), 'cohort identity: repeated cell'
for record in records:
    assert record['label'] == f"n{record['count']}-r{record['repeat']}", 'cohort identity: label/repeat mismatch'
    config = json.loads((root / record['label'] / 'config.json').read_bytes())
    assert config['source_sha'] == '8945c77a2603870dec3e5180a8f2daf0a9d42c60', 'cohort identity: mixed source'
rows, failures = [], []
for record in records:
    cell = root / record['label']
    verify_index(cell)
    config = json.loads((cell / 'config.json').read_bytes())
    count = config['count']
    assert count == record['count'] and config['rate'] == 100 and config['shards'] == 2
    assert config['memory_observer'] is False and config['bundle_mode'] == 'live-bundles'
    if record['status'] == 'FAIL_RETAINED':
        roles, cpu_samples, reported_cores = {}, {}, []
        for role in ('source', 'destination'):
            peer = cell / role / 'peer'
            verify_index(cell / role)
            verify_index(peer)
            env = json.loads((peer / 'environment.json').read_bytes())
            build = json.loads((peer / 'build-manifest.json').read_bytes())
            name = 'perf_rust_source' if role == 'source' else 'wp8_interop_server'
            selected = [0 if role == 'source' else 2]
            assert env['repository_sha'] == build['source_sha'] == config['source_sha']
            assert env['count'] == count and env['offered_rate'] == 100 and env['source_shards'] == 2
            assert env['bundle_mode'] == 'live-bundles' and env['memory_observer'] is False
            assert config[role]['cores'] == 1 and config[role]['cpu_pool'] == env['linux_environment']['selected_cpus'] == selected
            topology = next(v for v in env['linux_environment']['topology']['cpus'] if v['cpu'] == selected[0])
            reported_cores.append((topology['socket'], topology['core']))
            assert build['build_profile'] == 'release'
            assert digest(peer / 'executed-binary') == build['binary_sha256'][name] == env['binary_sha256'][name]
            samples = [json.loads(line) for line in (peer / 'resources.ndjson').read_text(encoding='utf-8').splitlines()]
            pid = json.loads((peer / 'pid.json').read_bytes())['pid']
            assert len(samples) > 2 and len({v['start_ticks'] for v in samples}) == 1
            assert all(v['pid'] == pid and v['affinity'] == selected for v in samples)
            assert all(b['timestamp_ns'] > a['timestamp_ns'] and b['cpu_ns'] >= a['cpu_ns'] for a, b in zip(samples, samples[1:]))
            cpu_samples[role] = samples
            forced = json.loads((peer / 'forced-cleanup.json').read_bytes()) if (peer / 'forced-cleanup.json').exists() else None
            if forced is not None:
                assert forced['group_killed'] is True
            udp = json.loads((peer / 'failure-udp.json').read_bytes())['roles'][role] if (peer / 'failure-udp.json').exists() else dict(status='NOT_MEASURED: process already exited')
            # Do not duplicate thousands of socket rows in the compact canonical analysis.
            sockets = udp.pop('sockets', [])
            if udp['status'] == 'MEASURED_FAILURE_SNAPSHOT':
                assert udp['pid'] == pid and udp['start_ticks'] == samples[0]['start_ticks']
                assert udp['udp_socket_count'] == len(sockets)
                assert udp['live_socket_drops'] == sum(v['drops'] for v in sockets)
            role_failure = json.loads((peer / 'failure.json').read_bytes()) if (peer / 'failure.json').exists() else None
            successful_peer = None
            if role_failure is None:
                check_endpoint(cell / role, role, count, memory_observer=False, bundle_mode='live-bundles')
                successful_peer = verified_individual_peer(peer, role, config['source_sha'], count)
            server = json.loads((peer / 'server-result.json').read_bytes()) if (peer / 'server-result.json').exists() else None
            roles[role] = dict(peak_rss_bytes=max(v['rss_bytes'] for v in samples), forced_cleanup=forced,
                               failure_udp=udp, failure=role_failure,
                               individually_verified_peer=successful_peer,
                               server_recorded_sample_count=len(server['samples']) if server is not None else None)

        assert len(set(reported_cores)) == 2
        end = min(v[-1]['timestamp_ns'] for v in cpu_samples.values())
        windows = {}
        for seconds in (1, 2, 5, 10):
            estimates = {}
            bounds = {}
            for role, samples in cpu_samples.items():
                contained = [v for v in samples if end - seconds * 10**9 <= v['timestamp_ns'] <= end]
                assert len(contained) > 1
                estimates[role] = (contained[-1]['cpu_ns'] - contained[0]['cpu_ns']) / (seconds * 10**9)
                bounds[role] = [contained[0]['timestamp_ns'], contained[-1]['timestamp_ns']]
            windows[str(seconds)] = dict(per_role_effective_core_estimate=estimates, allocated_two_guest_core_fraction_estimate=sum(estimates.values()) / 2, contained_sample_bounds=bounds)
        stdout = [json.loads(line) for line in (cell / 'source/peer/stdout').read_text(encoding='utf-8').splitlines()]
        failed = [v for v in stdout if v.get('success') is False]
        assert len({v['logical_client_id'] for v in failed}) == len(failed)
        assert record['owned_processes_absent_before_stop'] == {'source': True, 'destination': True}
        failures.append(dict(label=record['label'], status='FAIL_RETAINED', requested=count,
                             source_materialized_observation_rows=sum(v.get('phase') == 'b3_materialized_streams_ready' for v in stdout),
                             source_errors=dict(Counter(v['error'] for v in failed)),
                             source_recorded_successes=sum(v.get('success') is True for v in stdout),
                             final_ownership='NOT_ACCEPTED_FOR_PAIR: see individually verified role, failed role remains unmeasured',
                             owned_processes_absent_before_stop=record['owned_processes_absent_before_stop'],
                             cpu_windows=windows, roles=roles))
        continue
    result = analyze(cell / 'source/peer', cell / 'destination/peer', source_sha=config['source_sha'], count=count, memory_observer=False, bundle_mode='live-bundles')
    for role in ('source', 'destination'):
        check_endpoint(cell / role, role, count, memory_observer=False, bundle_mode='live-bundles')
        env = json.loads((cell / role / 'peer/environment.json').read_bytes())
        assert env['offered_rate'] == 100 and env['source_shards'] == 2
        assert config[role]['cores'] == 1
        assert config[role]['cpu_pool'] == env['linux_environment']['selected_cpus'] == [0 if role == 'source' else 2]
        assert all(type(result[role + '_cleanup'][field]) is int and result[role + '_cleanup'][field] == 0 for field in FIELDS)
    assert record['owned_processes_absent_before_stop'] == {'source': True, 'destination': True}
    cleanup = json.loads((cell / 'cleanup.json').read_bytes())
    assert all(not value['local_relay_forced'] for value in cleanup.values())
    rows.append(dict(label=record['label'], count=count, result=result))
print(json.dumps(dict(classification='FAILURE_ONLY_UDP_MIB_DIAGNOSTIC', attempted_trials=len(records),
    successful_trials=len(rows), failed_trials=len(failures), capacity_gate='NOT_EVALUATED: diagnostic control, all outcomes retained',
    successful_connections_in_passed_trials=sum(r['count'] for r in rows), successful_trials_final_ownership='ZERO' if rows else 'NO_SUCCESSFUL_TRIALS',
    private_memory='NOT_MEASURED: optional observer OFF', observer_neutrality='NOT_ESTABLISHED',
    marginal_cost='NOT_QUALIFIED: connection/session/channel/stream co-vary',
    scope='Docker/WSL split advertised guest cores sourceCPU0/destinationCPU2; no physical/server/capacity claim',
    cpu_basis='DERIVED tick-quantized contained-sample estimates on common Docker clock; not strict lower bounds or physical-core proof',
    attribution='Cumulative socket drops and tail CPU pressure are measured; per-timeout causation and observer effect remain unresolved',
    rows=rows, failures=failures), indent=2))
