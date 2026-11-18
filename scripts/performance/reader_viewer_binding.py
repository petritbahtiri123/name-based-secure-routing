"""Read-only arguments for the existing 8765 owner attachment publisher."""
import math
from pathlib import Path
import re


def attachment_arguments(root, run, request, ready, *, now, python):
    """Bind already authenticated owner records, not campaign acceptance.

    The separately supervised control-plane caller must pin and reread the source
    request/readiness bytes, verify the owner and charge publisher outputs. This
    pure adapter neither authenticates files nor grants workload authorization.
    No publication may be inserted inline in passive preparation or PRE/POST.
    """
    root = Path(root)
    if not root.is_absolute() or type(run) is not str or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', run):
        raise ValueError('explicit successor root/run required')
    if type(request) is not dict or type(ready) is not dict:
        raise ValueError('owner records required')
    anchor = request.get('trial_anchor')
    times = [anchor, now, request.get('started'), request.get('work_deadline'),
             request.get('cleanup_deadline'), ready.get('deadline')]
    if any(type(t) not in (int, float) or not math.isfinite(t) for t in times):
        raise ValueError('finite nonboolean owner times required')
    if not 0 <= anchor <= request['started'] <= now < anchor + 115:
        raise ValueError('original viewer observation window expired')
    if 'parent_end' in request or 'cleanup_purpose' in request or (request['work_deadline'], request['cleanup_deadline']) != (anchor + 170, anchor + 175):
        raise ValueError('fixed receiver ownership window')
    output = root / 'live-lab' / 'receiver-command'
    expected = [python, '-B', str(root / 'finite_receiver.py'), 'worker', str(output / 'request.json')]
    if request.get('argv') != expected or request.get('output') != str(output):
        raise ValueError('fixed receiver request identity')
    if ready != dict(run=run, deadline=anchor + 175, port=8766):
        raise ValueError('receiver readiness identity')
    return run, anchor, root / 'live-lab' / 'viewer-qualification.json'
