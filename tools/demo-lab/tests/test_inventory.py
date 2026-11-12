import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from nbsr_demo_lab.setup import inventory


def test_container_entrypoint_and_recipes_are_hashed(tmp_path):
    root = tmp_path / 'tools/demo-lab/container'
    root.mkdir(parents=True)
    for name in ('demo-container-worker', 'Dockerfile', 'Prepare.Dockerfile', 'Dockerfile.dockerignore'):
        (root / name).write_text('original')
    before = inventory(tmp_path)
    assert len(before) == 4
    (root / 'demo-container-worker').write_text('changed executable entrypoint')
    assert inventory(tmp_path) != before
