"""Execute the documented manifest recipe against synthetic build metadata."""

import json
from pathlib import Path
import subprocess

import pytest


SHA = 'a' * 40
DOC = Path(__file__).resolve().parents[2] / 'docs/benchmarks/EXTERNAL_LINUX_SERVER_VALIDATION.md'


@pytest.mark.parametrize('fault', [None, 'head-changed', 'dirty', 'existing-manifest'])
def test_recipe_never_relabels_or_overwrites_build_evidence(tmp_path, monkeypatch, fault):
    root, target = tmp_path / 'evidence', tmp_path / 'target'
    (root / 'raw').mkdir(parents=True)
    (target / 'release').mkdir(parents=True)
    (root / 'raw/source-sha.txt').write_text(SHA + '\n')
    for name in ('rustc', 'cargo'):
        (root / 'raw' / (name + '.txt')).write_text('synthetic toolchain')
    for name in ('perf_direct_peer', 'perf_rust_source', 'wp8_interop_server'):
        (target / 'release' / name).write_bytes(name.encode())
    manifest = root / 'build-manifest.json'
    if fault == 'existing-manifest':
        manifest.write_text('retained original')
    monkeypatch.setenv('NBSR_LINUX_BUILD_EVIDENCE', str(root))
    monkeypatch.setenv('CARGO_TARGET_DIR', str(target))

    def git(argv, **kwargs):
        if argv == ['git', 'rev-parse', 'HEAD']:
            return ('b' * 40 if fault == 'head-changed' else SHA) + '\n'
        assert argv == ['git', 'status', '--porcelain', '--untracked-files=all']
        return ' M source.rs\n' if fault == 'dirty' else ''

    monkeypatch.setattr(subprocess, 'check_output', git)
    recipe = DOC.read_text().split("python3 - <<'PY'\n", 1)[1].split('\nPY\n', 1)[0]
    if fault:
        with pytest.raises((ValueError, FileExistsError)):
            exec(compile(recipe, str(DOC), 'exec'), {})
        if fault == 'existing-manifest':
            assert manifest.read_text() == 'retained original'
        else:
            assert not manifest.exists()
    else:
        exec(compile(recipe, str(DOC), 'exec'), {})
        value = json.loads(manifest.read_text())
        assert value['source_sha'] == SHA and value['build_profile'] == 'release'
        assert len(value['binary_sha256']) == 3
