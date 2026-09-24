"""Reference-bound native diagnostics; never certify live observer or B5 stability."""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path

from scripts.performance.linux_b5_ceiling import require
from scripts.performance.linux_b5_placement import seal_output
from scripts.performance.linux_loopback import ROOT, digest, write_json
from scripts.performance.linux_native_duration import bounds
from scripts.performance.linux_native_finite_run import execute as run_finite, validate_config
from scripts.performance.linux_native_lifecycle_control import decode_object
from scripts.performance.linux_native_observer import placement_identity
from scripts.performance.linux_native_pair import read, verify_index
from scripts.performance.linux_native_reference import analyze_reference, _bind_reference
from scripts.performance.process_cancellation import Cancellation, not_cancelled


def execute(config, reference_manifest, *, percent, seconds, output,
            runner=run_finite, check_cancelled=not_cancelled):
    validate_config(config)
    require('diagnostic_rate' not in config and 'diagnostic_seconds' not in config,
            'reference derives pacing; remove caller rate/duration')
    require(seconds is not None, 'explicit diagnostic duration required')
    bounds(seconds)
    require(all(config.get(key, True) is True for key in
        ('post_close_reports', 'source_live_guard', 'paired_live_guards')),
        'reference diagnostic requires both live guards and cleanup reports')
    output = Path(output)
    require(not output.exists() and not output.is_symlink()
            and not output.resolve().is_relative_to(ROOT), 'fresh external output required')
    path = Path(reference_manifest)
    with path.open('rb') as stream:
        original = stream.read(65537)
    require(len(original) <= 65536, 'reference manifest bound exceeded')
    check_cancelled()
    reference = analyze_reference(path, source_sha=config['source_sha'])
    shape = dict(cores=config['source']['cores'], payload_bytes=config['payload'], streams=config['streams'])
    load = _bind_reference(reference, current_sha=config['source_sha'], identities=reference['identities'],
        shape=shape, path=config['path'], depth=config['depth'], percent=percent)
    require(all(config[role]['bind'] == reference['identities'][role]['bind']
                for role in ('source', 'destination')), 'declared bind/reference mismatch')
    require(digest(path) == load['manifest_sha256'] == hashlib.sha256(original).hexdigest(),
            'reference manifest changed during preflight')
    actual = deepcopy(config)
    actual.update(diagnostic_rate=[load['rate_numerator'], load['rate_denominator']],
        diagnostic_seconds=seconds, post_close_reports=True, source_live_guard=True, paired_live_guards=True)
    validate_config(actual)
    check_cancelled()
    output.mkdir(parents=False, exist_ok=False)
    try:
        (output / 'reference-manifest.json').write_bytes(original)
        write_json(output / 'reference-origin.json', dict(path=str(path.resolve()),
            note='relative reference paths resolve against this original directory, not the copied manifest'))
        write_json(output / 'reference-analysis.json', reference)
        write_json(output / 'derived-load.json', load)
        write_json(output / 'config.json', actual)
        outcome = runner(actual, output / 'run', check_cancelled=check_cancelled)
        run_index = verify_index(output / 'run')
        observed = {role: placement_identity(read(output / 'run' / role / 'peer', 'environment.json'))
                    for role in ('source', 'destination')}
        require(observed == reference['identities'], 'actual placement/build differs from reference')
        require(analyze_reference(path, source_sha=config['source_sha']) == reference,
                'reference evidence changed during execution')
        check_cancelled()
        result = dict(classification='REFERENCE_BOUND_DIAGNOSTIC', source_sha=config['source_sha'],
            reference_manifest_sha256=load['manifest_sha256'], derived_load=load,
            run_index_sha256=run_index, run=outcome, sustained_capacity='NOT_ESTABLISHED',
            live_observer_qualification='NOT_ESTABLISHED', external_hardware='NOT_PROVEN',
            placement_check='actual retained placement checked after execution; not remote attestation')
        write_json(output / 'result.json', result)
        return result
    except BaseException as error:
        write_json(output / 'failure.json', dict(status='INVALID_PARTIAL',
            error_type=type(error).__name__, error=str(error)))
        raise
    finally:
        seal_output(output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--reference', type=Path, required=True)
    parser.add_argument('--percent', type=int, choices=range(70, 81), required=True)
    parser.add_argument('--seconds', type=int, choices=(60, 3600, 7200), required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    with args.config.open('rb') as stream:
        config = decode_object(stream.read(65537))
    with Cancellation() as cancellation:
        result = execute(config, args.reference, percent=args.percent, seconds=args.seconds,
                         output=args.output, check_cancelled=cancellation.check)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
