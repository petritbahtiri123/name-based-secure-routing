"""Portable paired B5 placement diagnostic; never a sustained-capacity acceptance."""

import argparse
import json
import math
import os
from pathlib import Path
import platform
import shutil
import statistics
from types import SimpleNamespace

from scripts.performance import linux_b5_campaign as campaign
from scripts.performance.b3_linux import environment
from scripts.performance.linux_b5_ceiling import identity, require
from scripts.performance.linux_b5_reference import git_state
from scripts.performance.linux_loopback import ROOT, digest, write_json
from scripts.performance.process_cancellation import Cancellation, not_cancelled


def validate_result(row, placement, repeat):
    require(row.get('placement') == placement and row.get('repeat') == repeat,
            'placement/repeat identity mismatch')
    retained = row.get('classification') == 'FAIL_DIAGNOSTIC_RETAINED'
    require((retained and row.get('valid') is False
             and row.get('diagnostic_continue_on_performance_failure') is True
             and bool(row.get('diagnostic_gate_failures')))
            or (row.get('classification') == 'DIAGNOSTIC' and row.get('valid') is True),
            'incomplete or correctness failure; no replacement')
    require(not row.get('cleanup_errors'), 'cleanup failure; no continuation')
    final = row.get('final', {})
    require(final.get('errors') == 0 and final.get('timeouts') == 0
            and final.get('all_groups_joined') is True and final.get('evidence_valid') is True,
            'final correctness/cleanup failure')
    for field in ('gbps', 'window_p99_median_ns'):
        value = row.get(field)
        require(type(value) in (int, float) and math.isfinite(value) and value > 0,
                'missing positive finite cohort metric')


def dispersion(rows):
    return {placement: {field: campaign.cv([r[field] for r in rows if r['placement'] == placement])
            for field in ('gbps', 'window_p99_median_ns')} for placement in ('shared', 'split')}


def seal_output(output):
    index = output / 'checksums.sha256'
    entries = []
    for path in sorted(output.rglob('*')):
        require(not path.is_symlink(), 'symlink in evidence output')
        if path.is_file() and path != index:
            entries.append(f'{digest(path)}  {path.relative_to(output).as_posix()}\n')
    index.write_bytes(''.join(entries).encode())


def run_pairs(run, retain):
    rows, required, first_three = [], 3, None
    for repeat in range(1, 6):
        if repeat > required:
            break
        order = ('shared', 'split') if repeat % 2 else ('split', 'shared')
        for placement in order:
            row = run(placement, repeat)
            retain(row)
            validate_result(row, placement, repeat)
            rows.append(row)
        if repeat == 3:
            first_three = dispersion(rows)
            if any(v > .05 for metrics in first_three.values() for v in metrics.values()):
                required = 5
    cvs = dispersion(rows)
    medians = {p: {f: statistics.median(r[f] for r in rows if r['placement'] == p)
                  for f in ('gbps', 'window_p99_median_ns')} for p in ('shared', 'split')}
    return dict(classification='COMPLETE_DIAGNOSTIC', repeats_per_placement=required,
        failed_gate_runs=sum(r['classification'] == 'FAIL_DIAGNOSTIC_RETAINED' for r in rows),
        first_three_cv=first_three, final_cv=cvs,
        medians=medians,
        median_delta_percent={f: 100 * (medians['split'][f] / medians['shared'][f] - 1)
                              for f in medians['shared']},
        dispersion_unresolved=any(v > .05 for metrics in cvs.values() for v in metrics.values()),
        sustained_stability='NOT_PROVEN', observer_qualification='NOT_QUALIFIED',
        scope='One path at fixed offered rate; split allocates two guest CPUs versus one shared CPU',
        p99_definition='median of observed steady-window p99; not pooled-operation p99')


def execute_cell(args, placement, repeat, directory, *, check_cancelled=not_cancelled):
    child = SimpleNamespace(binaries=args.binaries, build_manifest=args.build_manifest,
        output=directory, diagnostic=True, retain_failed_diagnostic=True, reference=None,
        rate=args.rate, paths=[args.path], placement=placement, ownership_sampling=True,
        percent=70, payload=args.payload, streams=args.streams, depth=args.depth,
        warmup=args.warmup, duration=args.duration, progress=args.progress)
    error = None
    try:
        campaign.execute(child, check_cancelled=check_cancelled)
    except Exception as caught:
        error = caught
    records_path = directory / 'records.json'
    records = json.loads(records_path.read_bytes()) if records_path.exists() else []
    row = dict(records[0]) if len(records) == 1 else dict(valid=False, classification='FAIL')
    row.update(placement=placement, repeat=repeat, raw_directory=directory.name)
    expected_retention = (type(error) is RuntimeError
        and str(error) == 'invalid partial run retained; no replacement'
        and row.get('classification') == 'FAIL_DIAGNOSTIC_RETAINED')
    if error is not None and not expected_retention:
        row.update(valid=False, classification='FAIL', controller_error=str(error))
    progress_file = directory / f'raw/{args.path}-r1/source.stdout.ndjson'
    if progress_file.exists():
        values = []
        with progress_file.open() as stream:
            for line in stream:
                value = json.loads(line)
                if (value.get('event') == 'b5_grouped_progress' and value.get('phase') == 'steady'
                        and value.get('p99_latency_ns') is not None):
                    values.append(value['p99_latency_ns'])
        row['window_p99_median_ns'] = statistics.median(values) if values else None
    return row


def execute(args, *, check_cancelled=not_cancelled):
    require(platform.system() == 'Linux', 'Linux required; no platform fallback')
    require(0 < args.duration <= 600 and math.isfinite(args.duration), 'diagnostic duration must be <=600s')
    require(not any(name.startswith('NBSR_') for name in os.environ),
            'remove inherited NBSR experiment settings before execution')
    sha, dirty = git_state()
    require(not dirty, 'clean checkout required')
    output = args.output.resolve()
    require(not output.is_relative_to(ROOT), 'output must be outside checkout')
    linux = environment(2)
    initial_identity = identity(linux, selected_count=2)
    sources = {p: digest(ROOT / p) for p in (*campaign.SOURCE_PATHS,
                                           'scripts/performance/linux_b5_placement.py')}
    build_digest = digest(args.build_manifest)
    binaries = {p: digest(args.binaries / p) for p in campaign.NAMES.values()}

    def unchanged():
        check_cancelled()
        require(git_state() == (sha, ''), 'source changed')
        require(all(digest(ROOT / p) == h for p, h in sources.items()), 'controller changed')
        require(digest(args.build_manifest) == build_digest
                and all(digest(args.binaries / p) == h for p, h in binaries.items()), 'build changed')
        require(identity(environment(2), selected_count=2) == initial_identity, 'environment changed')

    output.mkdir(parents=True, exist_ok=False)
    rows = []
    try:
        write_json(output / 'environment.json', dict(repository_sha=sha, linux_environment=linux,
            source_sha256=sources, binary_sha256=binaries, build_manifest_sha256=build_digest,
            controller_args={k: str(v) if isinstance(v, Path) else v for k, v in vars(args).items()},
            scope='Loopback diagnostic; native hardware, observer and sustained acceptance require separate evidence'))
        shutil.copyfile(__file__, output / 'controller.py')

        def retain(row):
            rows.append(row)
            write_json(output / 'records.json', rows)

        def run(placement, repeat):
            unchanged()
            print(f'placement={placement} repeat={repeat}', flush=True)
            row = execute_cell(args, placement, repeat, output / f'{placement}-r{repeat}',
                               check_cancelled=check_cancelled)
            # Retain the cell even if post-run provenance verification fails.
            try:
                unchanged()
            except Exception as error:
                row.update(valid=False, classification='FAIL', provenance_error=str(error))
            return row

        write_json(output / 'summary.json', run_pairs(run, retain))
    except Exception as error:
        write_json(output / 'failure.json', dict(classification='INVALID_PARTIAL', error=str(error),
                                                retained=len(rows), replacement=False))
        raise
    finally:
        write_json(output / 'records.json', rows)
        seal_output(output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('binaries', 'build-manifest', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--rate', type=int, nargs=2, required=True, metavar=('NUMERATOR', 'DENOMINATOR'))
    parser.add_argument('--path', choices=('direct', 'nbsr'), default='nbsr')
    parser.add_argument('--payload', type=int, choices=(1024, 16384), default=16384)
    parser.add_argument('--streams', type=int, default=8)
    parser.add_argument('--depth', type=int, choices=(1, 2, 4, 8, 16), default=1)
    parser.add_argument('--warmup', type=float, default=3)
    parser.add_argument('--duration', type=float, default=300)
    parser.add_argument('--progress', type=float, default=30)
    args = parser.parse_args()
    with Cancellation() as cancellation:
        execute(args, check_cancelled=cancellation.check)


if __name__ == '__main__':
    main()
