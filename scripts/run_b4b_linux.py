"""Linux single-host Task4i admission ladder; builds are a separate prerequisite."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import run_b4b_task4i as task4i
from scripts.performance.b3_linux import environment
from scripts.performance.b4_linux import LinuxB4Backend
from scripts.run_b3_v2 import verify_linux_execution

ROOT = Path(__file__).resolve().parents[1]


def clean_sha():
    sha = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    if subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=all'], cwd=ROOT, text=True):
        raise ValueError('clean source checkout required')
    return sha


def validate_build(path, binaries, sha):
    wire = path.read_bytes()
    value = json.loads(wire)
    if (value.get('source_sha') != sha or value.get('build_profile') != 'release'
            or not value.get('build_commands') or not value.get('toolchains')):
        raise ValueError('release build/source metadata mismatch')
    for binary in binaries.values():
        if value.get('binary_sha256', {}).get(binary.name) != hashlib.sha256(binary.read_bytes()).hexdigest():
            raise ValueError('Linux binary digest mismatch')
    return value, hashlib.sha256(wire).hexdigest(), wire


def execute(args):
    sha = clean_sha()
    host = environment(args.cores)
    binaries = {'nbsr': args.target / 'release/perf_rust_source',
                'server': args.target / 'release/wp8_interop_server'}
    build, manifest_digest, manifest_wire = validate_build(args.build_manifest, binaries, sha)
    if args.output.resolve().is_relative_to(ROOT):
        raise ValueError('Linux raw output must be outside checkout')
    args.output.mkdir(parents=True, exist_ok=False)
    retained = args.output / 'binaries'
    retained.mkdir()
    try:
        for original in binaries.values():
            shutil.copy2(original, retained / original.name)
        def verify():
            if clean_sha() != sha:
                raise ValueError('source changed during run')
            verify_linux_execution(binaries, retained, build)
        verify()
        metadata = dict(schema='nbsr-b4-linux-definition-v1', repository_sha=sha,
                        dirty_tree=False, platform='linux', linux_environment=host,
                        binary_source_sha=build['source_sha'], input_build_manifest_sha256=manifest_digest,
                        build_manifest=build, execution_paths={k: str(v.resolve()) for k, v in binaries.items()},
                        retained_paths={k: str((retained / v.name).resolve()) for k, v in binaries.items()},
                        placement={'cpus': host['selected_cpus'], 'scope': 'all four owned peers share this pool'},
                        scope='Linux single-host loopback; no two-host or hardware-ceiling claim',
                        ownership_scope='exact source terminal markers plus existing destination gauges; source full ownership NOT_MEASURED')
        task4i.v2.write_json(args.output / 'definition.json', metadata)
        task4i.v2.write_json(args.output / 'build-manifest.json', build)
        (args.output / 'input-build-manifest.json').write_bytes(manifest_wire)
        backend = LinuxB4Backend(host['selected_cpus'], host['taskset'], verify_execution=verify)
        result = task4i.execute(args.output / 'campaign', offered_rates=args.offered_rates,
                               source_shards=args.source_shards, backend=backend,
                               prepared_binaries=binaries, prepared_environment=metadata)
        verify()
        return result
    except BaseException as error:
        task4i.v2.write_json(args.output / 'failure.json', {'classification': 'INVALID_PARTIAL_LINUX_B4',
                                  'error_type': type(error).__name__, 'partial_evidence_retained': True})
        raise
    finally:
        task4i.checksums(args.output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--target', type=Path, required=True)
    parser.add_argument('--build-manifest', type=Path, required=True)
    parser.add_argument('--cores', type=int, choices=(1, 2, 4), required=True)
    parser.add_argument('--source-shards', type=int, choices=(1, 2), default=1)
    parser.add_argument('--offered-rates', type=int, nargs='+', default=None)
    execute(parser.parse_args())


if __name__ == '__main__':
    main()
