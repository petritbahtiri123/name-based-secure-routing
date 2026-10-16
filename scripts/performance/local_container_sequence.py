"""Offline three-cell orchestration over a trusted injected workload adapter.

No subprocess, container engine, sockets, fixture creation, or live adapter exists
here. Commands are recipes only. A future adapter must materialize the exact config,
bind endpoints to the supplied container IDs, use the existing watchdog/finite
validators, and inject interruption after independently verified readiness.
"""
from dataclasses import dataclass
import json
from scripts.performance import native_debug_correctness as debug
from pathlib import PurePosixPath
import re
import sys

from scripts.performance.linux_native_finite_run import validate_config
from scripts.performance.linux_native_watchdog import worker_command
from scripts.performance.local_container_disposal import Controller, Unconfirmed


@dataclass(frozen=True)
class Cell:
    run: str
    config: dict
    config_path: str
    output: str


@dataclass(frozen=True)
class Plan:
    run: str
    interrupt: bool
    config_json: bytes
    owners: tuple
    worker_command: tuple
    watchdog_command: tuple


@dataclass(frozen=True)
class Outcome:
    """Trusted adapter result; readiness is explicitly simulated in offline tests."""

    status: str
    interrupted_after_ready: tuple = ()


@dataclass(frozen=True)
class Result:
    run: str
    status: str | None
    accepted: bool
    cleanup_confirmed: bool
    errors: tuple


def _plans(cells, baseline):
    if len(cells) != 3 or type(baseline) is not int or baseline < 8 * 2**30:
        raise Unconfirmed('three cells and original resource baseline required')
    runs, roots, configs, plans = set(), [], set(), []
    previous = None
    for index, cell in enumerate(cells):
        if (type(cell) is not Cell or type(cell.run) is not str
                or not re.fullmatch(r'[a-zA-Z0-9_-]{1,80}', cell.run) or cell.run in runs):
            raise Unconfirmed('fresh exact run required')
        runs.add(cell.run)
        config_json = json.dumps(cell.config, sort_keys=True, allow_nan=False).encode()
        config = json.loads(config_json)
        validate_config(config)
        if 'diagnostic_seconds' in config:
            raise Unconfirmed('long profiles exceed the existing watchdog contract')
        if config['path'] != 'nbsr' or config['streams'] != 2 or config.get('post_close_reports') is not True:
            raise Unconfirmed('two-stream NBSR with post-close reports required')
        if cell.config_path in configs:
            raise Unconfirmed('fresh config path required')
        configs.add(cell.config_path)
        for path in (cell.config_path, cell.output):
            if (type(path) is not str or not path.startswith('/') or '\\' in path
                    or '..' in path.split('/') or str(PurePosixPath(path)) != path):
                raise Unconfirmed('canonical absolute recipe path required')
        for root in (cell.output, config['source']['output'], config['destination']['output']):
            path = PurePosixPath(root)
            if any(path == old or path in old.parents or old in path.parents for old in roots):
                raise Unconfirmed('fresh disjoint output roots required')
            roots.append(path)
        comparison = json.loads(config_json)
        for role in ('source', 'destination'):
            comparison[role].pop('output')
        if previous is not None and comparison != previous:
            raise Unconfirmed('unchanged workload and provisioned identity required')
        previous = comparison
        worker = tuple(worker_command('finite', cell.config_path, cell.output + '/worker'))
        watchdog = (sys.executable, '-B', '-m', 'scripts.performance.linux_native_watchdog',
                    '--mode', 'finite', '--config', cell.config_path, '--output', cell.output,
                    '--original-disk-free-bytes', str(baseline))
        plans.append(Plan(cell.run, index == 1, config_json, (), worker, watchdog))
    for config_path in configs:
        path = PurePosixPath(config_path)
        if any(path == root or path in root.parents or root in path.parents for root in roots):
            raise Unconfirmed('configuration and fresh output roots must be disjoint')
    return plans


class Sequence:
    """Single-use offline sequence; every partial result and owner stays inspectable."""

    def __init__(self, engine):
        self.controller = Controller(engine)
        self._started = False
        self._results = []

    @property
    def results(self):
        return tuple(self._results)

    def run(self, cells, runner, *, original_disk_free_bytes):
        if self._started:
            raise Unconfirmed('sequence already attempted')
        plans = _plans(cells, original_disk_free_bytes)
        self._started = True
        for plan in plans:
            status, errors, receipts = None, [], []
            accepted = cleanup = False
            try:
                owners = self.controller.start(plan.run)
                bound = Plan(plan.run, plan.interrupt, plan.config_json, owners,
                             plan.worker_command, plan.watchdog_command)
                value = runner(bound)
                status = value.status if type(value) is Outcome and type(value.status) is str else None
                expected = 'INVALID_PARTIAL' if plan.interrupt else debug.status('PASS_CONTROLLED_FINITE_PAIR', json.loads(plan.config_json).get(debug.FIELD))
                ready = value.interrupted_after_ready if type(value) is Outcome else None
                expected_ready = owners if plan.interrupt else ()
                accepted = (status == expected and type(ready) is tuple
                            and len(ready) == len(expected_ready)
                            and all(a is b for a, b in zip(ready, expected_ready)))
                if not accepted:
                    errors.append('unexpected workload result')
            except BaseException as exc:
                errors.append(('workload_or_creation', type(exc).__name__))
            finally:
                # Continue to the other exact owner even when one cleanup fails.
                for owner in self.controller.owned:
                    try:
                        receipts.append(self.controller.dispose(owner))
                    except BaseException as exc:
                        errors.append(('disposal', owner.role, type(exc).__name__))
                try:
                    self.controller.release(tuple(receipts))
                    cleanup = True
                except Unconfirmed as exc:
                    errors.append(('release', type(exc).__name__))
                self._results.append(Result(plan.run, status, accepted, cleanup, tuple(errors)))
            if not accepted or not cleanup:
                raise Unconfirmed('sequence stopped; inspect retained results and ownership')
        return self.results
