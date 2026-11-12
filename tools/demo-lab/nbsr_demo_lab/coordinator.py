"""Single owner, fixed scenarios, idempotent requests, durable uncertain-run latch."""
import json
import platform
import re
import threading
import uuid
from pathlib import Path

SCENARIOS = {
    'allowed_service_a': ('Service A allowed', 'LIVE_ATTEMPT'),
    'unknown_service': ('Unknown service rejected', 'REGRESSION'),
    'stale_authority': ('Stale authority rejected', 'REGRESSION'),
    'digest_mismatch': ('Service binding mismatch rejected', 'REGRESSION'),
    'expired_mapping': ('Expired Mapping rejected', 'REGRESSION'),
    'shared_ip_isolation': ('Shared IP service isolation', 'REGRESSION'),
}


class Coordinator:
    def __init__(self, repo, state):
        self.repo = Path(repo).resolve()
        self.state = Path(state)
        if self.state.is_symlink():
            raise ValueError('State symlink rejected')
        self.state.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.current = None
        self.lock = threading.RLock()
        self.cancel_event = threading.Event()
        self.thread = None
        self.requests = {}
        self.blocked = (self.state / 'active.json').exists()

    @property
    def running(self):
        return self.thread is not None and self.thread.is_alive()

    def status(self):
        with self.lock:
            return {'scenarios': [{'id': k, 'label': v[0], 'kind': v[1],
                                  'disabled': platform.system() not in ('Windows', 'Darwin')} for k, v in SCENARIOS.items()],
                    'current': self.current, 'blocked': self.blocked, 'running': self.running,
                    'platform_validation': ('Mac host / Linux container: prepared but UNTESTED; compatibility unknown' if platform.system() == 'Darwin'
                                            else 'Windows demo: locally tested, including personal Windows testing. See each run receipt for its outcome.')}

    def start(self, scenario, request_id):
        if not isinstance(scenario, str) or scenario not in SCENARIOS:
            raise ValueError('Scenario not allowlisted')
        if platform.system() not in ('Windows', 'Darwin'):
            raise ValueError('Interactive host must be Windows or Mac')
        if not isinstance(request_id, str) or not re.fullmatch(r'[a-zA-Z0-9-]{1,64}', request_id):
            raise ValueError('Invalid request ID')
        with self.lock:
            if request_id in self.requests:
                previous = self.requests[request_id]
                if previous['scenario'] != scenario:
                    raise ValueError('Request ID already belongs to another scenario')
                return previous
            if self.blocked or self.running:
                raise RuntimeError('A run is active or cleanup is unconfirmed; no new work admitted')
            if platform.system() == 'Darwin':
                from .mac import validate
                validate(self.repo, self.state)
            else:
                from .setup import validate_build
                validate_build(self.repo, self.state)
            run_id = 'demo-' + uuid.uuid4().hex
            with (self.state / 'active.json').open('x', encoding='utf-8') as file:
                file.write(json.dumps({'run_id': run_id, 'scenario': scenario}))
            self.blocked = True
            self.current = {'run_id': run_id, 'scenario': scenario, 'status': 'RUNNING', 'cleanup': 'PENDING'}
            self.requests[request_id] = {'run_id': run_id, 'scenario': scenario}
            self.cancel_event.clear()
            self.thread = threading.Thread(target=self._execute, args=(run_id, scenario), daemon=False)
            self.thread.start()
            return self.requests[request_id]

    def _execute(self, run_id, scenario):
        try:
            if platform.system() == 'Darwin':
                from .mac import execute
            else:
                from .runner import execute
            outcome = execute(self.repo, self.state, run_id, scenario, self.cancel_event)
            with self.lock:
                self.current = {'run_id': run_id, 'scenario': scenario, 'status': outcome['outcome'],
                                'cleanup': outcome['cleanup'], 'scenario_outcome': outcome['scenario_outcome'],
                                'errors': outcome['errors'],
                                'verify_command': f'{"python" if platform.system() == "Windows" else "python3"} tools/demo-lab/demo.py verify --run-id {run_id}'}
                if outcome['cleanup'] == 'CLEAN':
                    (self.state / 'active.json').unlink()
                    self.blocked = False
        except Exception as exc:
            with self.lock:
                self.current = {'run_id': run_id, 'scenario': scenario, 'status': 'INCOMPLETE',
                                'cleanup': 'UNCONFIRMED', 'errors': [type(exc).__name__ + ': ' + str(exc)]}

    def cancel(self):
        self.cancel_event.set()

    def close(self):
        self.cancel()
        if self.thread:
            self.thread.join(timeout=120)
