"""Explicitly approved local-only disk boundary. No remote configuration changes."""
import pathlib,shutil,json
from accounting import snapshot
START_FREE=11*1024**3
RUN_FREE=10*1024**3
ADDITIONAL_BYTES=256*1024**2
HERE=pathlib.Path(__file__).resolve().parent
def check_free(free,*,starting):
    if free<(START_FREE if starting else RUN_FREE):
        raise RuntimeError('local disk admission reserve' if starting else 'local disk running reserve')
def check_growth(current,baseline):
    if current-baseline>ADDITIONAL_BYTES:
        raise RuntimeError('256 MiB additional task write allowance')
def check(*,starting,groups=None):
    check_free(shutil.disk_usage(HERE.anchor).free,starting=starting)
    baseline=json.loads((HERE/'write-baseline.json').read_text())
    root=HERE.parent
    counts=snapshot(root,groups or {})
    check_growth(counts['task'],baseline['task_bytes'])
    return counts
