"""Read-only finite native reference gates; live B5 guards are a separate requirement."""

import argparse
from fractions import Fraction
import json
from pathlib import Path
import statistics

from scripts.performance.linux_b5_ceiling import require
from scripts.performance.linux_b5_reference import finish_record
from scripts.performance.linux_loopback import digest, repeat_target
from scripts.performance.linux_native_lifecycle_control import decode_object
from scripts.performance.linux_native_observer import placement_identity, qualify
from scripts.performance.linux_native_pair import analyze_pair, read
from scripts.performance.physical_core_analysis import classify_ladder


def analyze_reference(manifest_path, *, source_sha):
    path = Path(manifest_path)
    original_hash = digest(path)
    try:
        with path.open('rb') as stream:
            manifest = decode_object(stream.read(65537))
        require(set(manifest) == {'schema', 'depths', 'attempts', 'observers'}
                and manifest['schema'] == 'nbsr-native-reference-v1', 'invalid native reference manifest')
        depths, attempts, observers = (manifest[key] for key in ('depths', 'attempts', 'observers'))
        require(type(depths) is list and depths and depths[0] == 1
                and all(type(depth) is int and depth in (1, 2, 4, 8, 16) for depth in depths)
                and depths == sorted(set(depths)), 'ordered depth ladder beginning at one required')
        require(type(attempts) is list and 6 <= len(attempts) <= 50
                and type(observers) is dict and set(observers) == {str(depth) for depth in depths},
                'complete bounded ladder and observer manifests required')
        require(all(type(entry) is dict and set(entry) == {'path', 'depth', 'repeat', 'source', 'destination'}
                    and type(entry['depth']) is int and entry['depth'] in depths for entry in attempts),
                'invalid reference attempt')
        grouped = {depth: [entry for entry in attempts if entry['depth'] == depth] for depth in depths}
        require([entry['depth'] for entry in attempts] == [depth for depth in depths for _ in grouped[depth]],
                'depth ladder order mismatch')
        rows, indexes, roots_seen, identities, certificates = [], set(), set(), {}, {}
        shape = None
        for depth, entries in grouped.items():
            require(len(entries) in (6, 10), 'three or five complete matched repeats required')
            for sequence, entry in enumerate(entries):
                repeat = sequence // 2 + 1
                order = ('direct', 'nbsr') if repeat % 2 else ('nbsr', 'direct')
                require(type(entry['repeat']) is int and entry['repeat'] == repeat
                        and entry['path'] == order[sequence % 2], 'reference repeat/order mismatch')
                roots = {}
                for role in ('source', 'destination'):
                    require(type(entry[role]) is str and entry[role], 'missing reference peer root')
                    root = (path.parent / entry[role]).resolve()
                    require(root not in roots_seen, 'duplicate reference peer root')
                    roots_seen.add(root)
                    roots[role] = root
                pair = analyze_pair(roots['source'], roots['destination'], source_sha=source_sha)
                cell = pair['cell']
                require(set(cell) == {'path', 'cores', 'payload_bytes', 'streams', 'outstanding'}
                        and cell['path'] == entry['path'] and cell['outstanding'] == depth and cell['cores'] == 1,
                        'unpaced single-core reference workload required')
                current_shape = {key: cell[key] for key in ('cores', 'payload_bytes', 'streams')}
                shape = current_shape if shape is None else shape
                require(shape == current_shape, 'reference shape mismatch')
                for role, root in roots.items():
                    index = pair[role + '_index_sha256']
                    require(index not in indexes, 'duplicate reference evidence bytes')
                    indexes.add(index)
                    env = read(root, 'environment.json')
                    require(env.get('post_close_reports') is True and env.get('live_socket_observer', False) is False
                            and env.get('phase_control_endpoint') is None, 'reference observer mode mismatch')
                    current = placement_identity(env)
                    require(role not in identities or identities[role] == current, 'reference placement/build mismatch')
                    identities[role] = current
                    key = depth, repeat, role
                    require(key not in certificates or certificates[key] == env['certificates_sha256'],
                            'matched Direct/NBSR authority mismatch')
                    certificates[key] = env['certificates_sha256']
                row = finish_record(cell, repeat, read(roots['source'], 'validated-result.json'), cleanup_pass=True)
                row.update(source_index_sha256=pair['source_index_sha256'], destination_index_sha256=pair['destination_index_sha256'])
                rows.append(row)
            # Five is also valid when deliberately chosen before observing dispersion.
            first = {mode: [row['aggregate_application_gbps'] for row in rows
                           if row['path'] == mode and row['outstanding_per_stream'] == depth][:3]
                     for mode in ('direct', 'nbsr')}
            require(len(entries) == 10 or all(repeat_target(values) == 3 for values in first.values()),
                    'first-three dispersion requires five matched repeats')
        qualifications = {}
        for depth in depths:
            require(type(observers[str(depth)]) is str and observers[str(depth)], 'observer manifest path required')
            observed = qualify(path.parent / observers[str(depth)], source_sha=source_sha)
            require(observed['shape'] == dict(path='nbsr', outstanding=depth, **shape)
                    and observed['identities'] == identities, 'observer/reference workload or placement mismatch')
            qualifications[str(depth)] = observed
        ladders = {mode: classify_ladder([row for row in rows if row['path'] == mode]) for mode in ('direct', 'nbsr')}
        qualified = all(value['qualified'] for value in qualifications.values()) and all(
            value['strict_stable_gbps'] is not None for value in ladders.values())
        require(digest(path) == original_hash, 'reference manifest changed')
        return dict(schema='nbsr-native-reference-analysis-v1', source_sha=source_sha,
            manifest_sha256=original_hash, qualified=qualified, shape=shape, identities=identities,
            rows=rows, observers=qualifications, ladders=ladders, external_hardware='NOT_PROVEN',
            scope='finite closed-loop native placement only; not offered-rate sustainability or a host ceiling',
            coverage='all listed attempts; undisclosed attempts cannot be detected; declared order not attested')
    except (KeyError, IndexError, TypeError, OSError) as error:
        raise ValueError('incomplete/malformed native reference: ' + str(error)) from error


def load_reference(manifest_path, *, current_sha, identities, shape, path, depth, percent):
    require(path in ('direct', 'nbsr') and type(depth) is int
            and type(percent) is int and 70 <= percent <= 80, 'explicit 70–80 percent native load required')
    result = analyze_reference(manifest_path, source_sha=current_sha)
    return _bind_reference(result, current_sha=current_sha, identities=identities,
                           shape=shape, path=path, depth=depth, percent=percent)


def _bind_reference(result, *, current_sha, identities, shape, path, depth, percent):
    """Internal: only an immediately verified analysis, never user-supplied JSON."""
    require(path in ('direct', 'nbsr') and type(depth) is int
            and type(percent) is int and 70 <= percent <= 80, 'explicit 70–80 percent native load required')
    require(result['source_sha'] == current_sha, 'reference source mismatch')
    require(result['qualified'] and result['identities'] == identities and result['shape'] == shape,
            'qualified current-source/placement/shape reference required')
    selected = next((cell for cell in result['ladders'][path]['cells'] if cell['outstanding_per_stream'] == depth), None)
    require(selected is not None and selected['classification'] == 'STABLE', 'selected native depth is not strict stable')
    rows = [row for row in result['rows'] if row['path'] == path and row['outstanding_per_stream'] == depth]
    rate = statistics.median(Fraction(row['completed_operations'] * 1_000_000_000, row['measured_ns'])
                             for row in rows) * Fraction(percent, 100)
    require(0 < rate.numerator < 2**64 and 0 < rate.denominator < 2**64, 'unrepresentable native paced rate')
    return dict(mode='QUALIFIED_NATIVE_FINITE_REFERENCE', source_sha=current_sha,
        manifest_sha256=result['manifest_sha256'], path=path, depth=depth, percent=percent,
        rate_numerator=rate.numerator, rate_denominator=rate.denominator, shape=shape,
        identities=identities, external_hardware='NOT_PROVEN', sustained_capacity='NOT_ESTABLISHED')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--source-sha', required=True)
    args = parser.parse_args()
    result = analyze_reference(args.manifest, source_sha=args.source_sha)
    print(json.dumps(result, indent=2))
    if not result['qualified']:
        raise SystemExit(2)


if __name__ == '__main__':
    main()
