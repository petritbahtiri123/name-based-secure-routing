"""Reject cohort identity errors before opening per-process telemetry."""

import json
from pathlib import Path
import runpy
import sys

import pytest

from scripts.performance.linux_b5_placement import seal_output


@pytest.mark.parametrize('mutation', ['duplicate-cell', 'mixed-sha'])
def test_bundle_cohort_identity_preflight(tmp_path, monkeypatch, mutation):
    rows = []
    for count in (16, 32, 64, 128, 256, 512, 1024):
        for repeat in (1, 2, 3):
            label = f'n{count}-r{repeat}'
            cell = tmp_path / label
            cell.mkdir()
            config = dict(count=count, rate=100, shards=2, memory_observer=True,
                          source_sha='c5b53c66a12ba5fa59a2d9d97ef724ec27d50928')
            if mutation == 'mixed-sha' and count == 32 and repeat == 1:
                config['source_sha'] = 'a' * 40
            (cell / 'config.json').write_text(json.dumps(config), encoding='utf-8')
            seal_output(cell)
            rows.append(dict(label=label, count=count, repeat=repeat, status='PASS_FUNCTIONAL'))
    if mutation == 'duplicate-cell':
        rows[1]['label'] = rows[0]['label']
    (tmp_path / 'records.json').write_text(json.dumps(rows), encoding='utf-8')
    seal_output(tmp_path)
    analyzer = Path(__file__).resolve().parents[2] / 'evidence/performance/v2/native-bundle-memory-c5b53c66/analyze.py'
    monkeypatch.setattr(sys, 'argv', [str(analyzer), str(tmp_path)])
    with pytest.raises(AssertionError, match='cohort identity'):
        runpy.run_path(str(analyzer), run_name='__main__')
