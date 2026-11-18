"""Actual successor supervisor and handoff; deterministic owner, no processes."""
import ast
import math
from pathlib import Path
import time

import pytest

from scripts.performance.reader_handoff import ReaderHandoff


def supervisor():
    source = Path(__file__).with_name('fixtures') / 'reader_watchdog.py.snapshot'
    node = next(n for n in ast.parse(source.read_bytes()).body
                if isinstance(n, ast.FunctionDef) and n.name == 'supervise')
    ns = dict(time=time, math=math, COORDINATOR=6, WRAPPER=8,
              not_cancelled=lambda: None)
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(source), 'exec'), ns)
    return ns['supervise']


class Native:
    argv = ('fixture-reader',)
    deadline = 8.0
    cancelled = killed = False
    drain_failure = None

    def __init__(self, code=0):
        self.started = self.assigned = False
        self.job = self.process = self.thread = None
        self.observations = self.reaps = 0
        self.code = code

    @property
    def owned(self):
        return self.job is not None

    def start(self):
        self.started = self.assigned = True
        self.job, self.process, self.thread = object(), object(), object()

    def observe(self):
        self.observations += 1
        return (None, True) if self.observations == 1 else (self.code, False)

    def reap(self):
        assert self.owned
        self.reaps += 1
        self.job = self.process = self.thread = None

    def signal(self, signal):
        self.killed = signal == 'KILL'


def exercise(failure=None, code=0, handoff_enabled=True):
    native = Native(code)
    captures = []
    clock = [0.0]

    def capture(identity):
        captures.append(identity)
        return dict(identity, quiescent=True, final_valid=True, sha256='a' * 64)

    handoff = ReaderHandoff(run='r', source='s', request_sha256='b' * 64,
        argv=native.argv, anchor=0., deadline=8., caps={'capture': 64, 'receipts': 64},
        clock=lambda: clock[0], capture=capture)

    def fail_at_boundary(kind):
        if failure == kind and native.observations >= 2:
            raise RuntimeError('late ' + kind)

    def guard():
        fail_at_boundary('guard')
        if handoff_enabled:
            handoff.checkpoint(native)

    def sleep(seconds):
        clock[0] += max(seconds, .001)

    result = supervisor()(native, clock=lambda: clock[0], sleep=sleep,
        started_at=0., guard=guard, check_cancelled=lambda: fail_at_boundary('cancel'),
        closure_check=handoff.consume if handoff_enabled else None,
        closure_failure=handoff.invalidate if handoff_enabled else None)
    return result, native, handoff, captures


def test_exit_between_checkpoint_and_observe_uses_handoff_once():
    result, native, handoff, captures = exercise()
    assert result['status'] == 'LOCAL_WORKER_COMPLETED'
    assert handoff.consumed and handoff.lifecycle.state == 'CLOSED_UNSETTLED'
    assert native.reaps == len(captures) == 1
    assert not native.owned


@pytest.mark.parametrize('failure', ['guard', 'cancel'])
def test_boundary_failure_cleans_up_but_cannot_accept(failure):
    result, native, handoff, captures = exercise(failure)
    assert result['status'] == 'INVALID_PARTIAL'
    assert handoff.failed and handoff.lifecycle.state == 'INVALID'
    assert native.reaps == 1 and not native.owned and captures == []
    with pytest.raises(ValueError):
        handoff.consume(native)


def test_nonzero_exit_stays_invalid():
    result, native, handoff, captures = exercise(code=1)
    assert result['status'] == 'INVALID_PARTIAL'
    assert handoff.failed and native.reaps == 1 and captures == []


def test_no_handoff_retains_original_cleanup():
    result, native, _, captures = exercise(handoff_enabled=False)
    assert result['status'] == 'LOCAL_WORKER_COMPLETED'
    assert native.reaps == 1 and not native.owned and captures == []


def test_project_ci_selects_this_regression():
    from scripts.ci.check import command_groups
    commands = command_groups('python-core')
    assert any('tests/performance/test_reader_watchdog_handoff.py' in command.argv
               for command in commands)
