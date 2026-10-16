"""Deterministic handles and clocks only; no Windows process or Docker execution."""
import importlib
import json
from pathlib import Path

import pytest


def api():
    name = 'scripts.performance.windows_native_management'
    assert importlib.util.find_spec(name) is not None, 'Windows adapter missing'
    return importlib.import_module(name)


class Backend:
    def __init__(self, failure=None):
        self.actions = []
        self.failure = failure
        self.code = None
        self.active = 1

    def action(self, name, *args):
        self.actions.append((name, *args))
        if name == self.failure:
            raise OSError(name)

    def create_job(self):
        self.action('job')
        return 'job'

    def create_suspended(self, argv):
        self.action('suspended', tuple(argv))
        return 'process', 'thread'

    def assign(self, job, process):
        self.action('assign', job, process)

    def resume(self, thread):
        self.action('resume', thread)

    def observe(self, job, process, assigned):
        self.action('observe', job, process, assigned)
        return self.code, self.active

    def terminate(self, job, process, assigned):
        self.action('kill', job, process, assigned)

    def close(self, handle):
        self.action('close', handle)


def test_suspended_child_is_assigned_before_resume():
    mod = api()
    backend = Backend()
    owner = mod.WindowsOwner(['python', 'worker'], backend=backend, cancel=lambda: None)
    owner.start()
    assert [a[0] for a in backend.actions] == ['job', 'suspended', 'assign', 'resume']
    assert owner.owned
    assert owner.observe() == (None, True)


@pytest.mark.parametrize('failure', ['assign', 'resume'])
def test_start_failure_retains_exact_suspended_process_for_cleanup(failure):
    mod = api()
    backend = Backend(failure)
    owner = mod.WindowsOwner(['python', 'worker'], backend=backend, cancel=lambda: None)
    with pytest.raises(OSError):
        owner.start()
    assert owner.owned
    if failure == 'assign':
        assert not any(a[0] == 'resume' for a in backend.actions)
    backend.failure = None
    owner.signal('KILL')
    assert backend.actions[-1] == ('kill', 'job', 'process', failure != 'assign')


def test_cancel_latches_once_and_reap_requires_whole_job_absence():
    mod = api()
    backend, requests = Backend(), []
    owner = mod.WindowsOwner(['python', 'worker'], backend=backend,
                             cancel=lambda: requests.append('cancel'))
    owner.start()
    owner.signal('INT')
    owner.signal('TERM')
    assert requests == ['cancel']
    backend.code = 0
    assert owner.observe() == (0, True)
    with pytest.raises(mod.Unconfirmed):
        owner.reap()
    assert owner.owned
    backend.active = 0
    owner.reap()
    assert not owner.owned
    assert [a for a in backend.actions if a[0] == 'close'] == [
        ('close', 'thread'), ('close', 'process'), ('close', 'job')]


def test_reap_failure_retains_handles_without_double_close():
    mod = api()
    backend = Backend()
    owner = mod.WindowsOwner(['python', 'worker'], backend=backend, cancel=lambda: None)
    owner.start()
    backend.code, backend.active = 0, 0
    backend.failure = 'close'
    with pytest.raises(OSError):
        owner.reap()
    assert owner.owned
    backend.failure = None
    owner.reap()
    assert not owner.owned


@pytest.mark.parametrize('invalid', [(0, False), (True, 0), (0, -1)])
def test_invalid_job_observation_never_proves_cleanup(invalid):
    mod = api()
    backend = Backend()
    owner = mod.WindowsOwner(['python', 'worker'], backend=backend, cancel=lambda: None)
    owner.start()
    backend.code, backend.active = invalid
    with pytest.raises(mod.Unconfirmed):
        owner.observe()
    assert owner.owned


def test_shared_deadline_covers_creation_execution_and_cleanup_without_reset():
    mod = api()
    now = [10.0]
    budget = mod.CellBudget(clock=lambda: now[0])
    now[0] = 105.0
    with pytest.raises(TimeoutError):
        budget.check_work()
    assert budget.remaining_cleanup() == 25
    now[0] = 130.0
    with pytest.raises(TimeoutError):
        budget.remaining_cleanup()


def test_backward_clock_permanently_invalidates_budget():
    mod = api()
    now = [10.0]
    budget = mod.CellBudget(clock=lambda: now[0])
    now[0] = 9.0
    with pytest.raises(mod.Unconfirmed):
        budget.check_work()
    now[0] = 11.0
    with pytest.raises(mod.Unconfirmed):
        budget.remaining_cleanup()


def test_config_binds_exact_fresh_ids_without_changing_workload():
    mod = api()
    from scripts.performance.local_container_disposal import Container
    from scripts.performance.local_container_sequence import Plan
    config = json.loads(Path('docs/benchmarks/sphere-offline-20261012/'
                             'finite-two-stream.synthetic.json').read_text())
    owners = tuple(Container('one', role, digit * 64, True)
                   for role, digit in [('source', 'a'), ('destination', 'b')])
    plan = Plan('one', False, json.dumps(config).encode(), owners, (), ())
    bound = mod.bind_config(plan)
    assert bound['source']['host'] == 'a' * 64
    assert bound['destination']['host'] == 'b' * 64
    for role in ('source', 'destination'):
        assert bound[role]['transport'] == 'docker'
        bound[role]['host'], bound[role]['transport'] = config[role]['host'], config[role]['transport']
    assert bound == config


def test_bad_owner_role_run_or_id_rejected_before_worker():
    mod = api()
    from scripts.performance.local_container_disposal import Container
    from scripts.performance.local_container_sequence import Plan
    for owners in ((), (Container('wrong', 'source', 'a' * 64, True),),
                   (Container('one', 'source', 'alias', True),
                    Container('one', 'destination', 'b' * 64, True))):
        with pytest.raises(mod.Unconfirmed):
            mod.bind_config(Plan('one', False, b'{}', owners, (), ()))


def test_existing_watchdog_does_not_restart_budget_after_slow_creation():
    from scripts.performance.linux_native_watchdog import supervise
    import inspect
    assert 'started_at' in inspect.signature(supervise).parameters, 'shared absolute start missing'
    mod = api()
    now = [94.0]
    backend = Backend()
    owner = mod.WindowsOwner(['python', 'worker'], backend=backend, cancel=lambda: None)
    budget = mod.CellBudget(clock=lambda: 0.0)
    budget.clock = lambda: now[0]

    def sleep(seconds):
        now[0] += seconds

    result = supervise(owner, started_at=budget.started, clock=lambda: now[0], sleep=sleep,
                       check_cancelled=budget.check_work)
    assert now[0] <= 120.000001
    assert result['status'] == 'INVALID_PARTIAL'
    assert owner.owned
    assert any(a[0] == 'kill' for a in backend.actions)


def bound_plan(interrupt):
    from scripts.performance.local_container_disposal import Container
    from scripts.performance.local_container_sequence import Plan
    config = json.loads(Path('docs/benchmarks/sphere-offline-20261012/'
                             'finite-two-stream.synthetic.json').read_text())
    config.update(diagnostic_rate=[100, 1], source_live_guard=True, paired_live_guards=True)
    owners = tuple(Container('one', role, digit * 64, True)
                   for role, digit in [('source', 'a'), ('destination', 'b')])
    return Plan('one', interrupt, json.dumps(config).encode(), owners, (), ())


def test_worker_reuses_finite_validation_and_exact_binding(tmp_path, monkeypatch):
    mod = api()
    assert hasattr(mod, 'execute_bound'), 'bound coordinator adapter missing'
    seen = []

    def execute(config, output, **kwargs):
        seen.append(config)
        assert callable(kwargs['check_cancelled'])
        assert config['source']['host'] == 'a' * 64
        return {'status': 'PASS_CONTROLLED_FINITE_PAIR'}

    monkeypatch.setattr(mod.finite, 'execute', execute)
    result = mod.execute_bound(bound_plan(False), tmp_path / 'worker', check_cancelled=lambda: None)
    assert result.status == 'PASS_CONTROLLED_FINITE_PAIR'
    assert result.interrupted_after_ready == ()
    assert len(seen) == 1


@pytest.mark.parametrize('case', ['positive', 'zero_progress', 'unrelated_failure'])
def test_interruption_requires_validated_progress_and_exact_failure(tmp_path, monkeypatch, case):
    mod = api()
    assert hasattr(mod, 'execute_bound'), 'bound coordinator adapter missing'
    plan, output = bound_plan(True), tmp_path / 'worker'

    def execute(config, output, **kwargs):
        output.mkdir()
        try:
            if case == 'unrelated_failure':
                raise InterruptedError('unrelated')
            kwargs['on_validated_event']('source', {
                'event': 'paced_progress', 'value': {'completed': 1 if case == 'positive' else 0}})
            return {'status': 'PASS_CONTROLLED_FINITE_PAIR'}
        except BaseException as exc:
            (output / 'failure.json').write_text(json.dumps(
                {'status': 'INVALID_PARTIAL', 'error_type': type(exc).__name__}))
            raise

    monkeypatch.setattr(mod.finite, 'execute', execute)
    if case == 'positive':
        result = mod.execute_bound(plan, output, check_cancelled=lambda: None)
        assert result.status == 'INVALID_PARTIAL'
        assert all(a is b for a, b in zip(result.interrupted_after_ready, plan.owners))
    else:
        with pytest.raises((mod.Unconfirmed, InterruptedError)):
            mod.execute_bound(plan, output, check_cancelled=lambda: None)


def test_finite_hook_only_runs_after_ledger_acceptance(tmp_path, monkeypatch):
    from scripts.performance import linux_native_finite_run as finite
    import inspect
    assert 'on_validated_event' in inspect.signature(finite.execute).parameters, 'validated hook missing'
    seen = []
    config = api().bind_config(bound_plan(True))

    def drive(start, wait, send, finish):
        manager = wait.__self__
        # Real Manager and ledger reject an out-of-order telemetry event first.
        manager.messages.put(('source', b'{"event":"paced_progress"}\n'))
        manager.pump(0)

    monkeypatch.setattr(finite, 'drive', drive)
    with pytest.raises(ValueError):
        finite.execute(config, tmp_path / 'worker', on_validated_event=lambda *a: seen.append(a))
    assert seen == []
    assert json.loads((tmp_path / 'worker' / 'failure.json').read_text())['status'] == 'INVALID_PARTIAL'


def test_native_configuration_close_failure_keeps_job_handle():
    mod = api()
    from scripts.performance.windows_job_backend import RetainedJobError
    backend = Backend()

    def create_job():
        raise RetainedJobError('retained-job')

    backend.create_job = create_job
    owner = mod.WindowsOwner(['python', 'worker'], backend=backend, cancel=lambda: None)
    with pytest.raises(RetainedJobError):
        owner.start()
    assert owner.owned
    owner.reap()
    assert backend.actions == [('close', 'retained-job')]


@pytest.mark.parametrize('fault', [None, 'stale_reply', 'missing_reply', 'live_descendant'])
def test_windows_workload_requires_exact_reply_and_empty_job(tmp_path, fault):
    mod = api()
    assert hasattr(mod, 'WindowsWorkload'), 'Windows workload adapter missing'
    import hashlib
    now = [0.0]
    budget = mod.CellBudget(clock=lambda: now[0])

    class WorkerBackend(Backend):
        def create_suspended(self, argv):
            self.request = Path(argv[-1])
            return super().create_suspended(argv)

        def resume(self, thread):
            super().resume(thread)
            self.code = 0
            self.active = 1 if fault == 'live_descendant' else 0
            if fault != 'missing_reply':
                reply = {'request_sha256': hashlib.sha256(self.request.read_bytes()).hexdigest(),
                         'status': 'PASS_CONTROLLED_FINITE_PAIR', 'interrupted_after_ready': False}
                if fault == 'stale_reply':
                    reply['request_sha256'] = '0' * 64
                (self.request.parent / 'reply.json').write_text(json.dumps(reply))

        def terminate(self, *args):
            super().terminate(*args)
            self.code, self.active = 1, 0

    backend = WorkerBackend()
    runner = mod.WindowsWorkload(tmp_path, budget_for=lambda run: budget,
                                backend_factory=lambda: backend, guard=lambda: None,
                                sleep=lambda seconds: now.__setitem__(0, now[0] + seconds))
    if fault:
        with pytest.raises(mod.Unconfirmed):
            runner(bound_plan(False))
    else:
        assert runner(bound_plan(False)).status == 'PASS_CONTROLLED_FINITE_PAIR'
    assert now[0] <= 120
    assert not runner.owner.owned
    assert (tmp_path / 'one' / 'supervision.json').exists()


def test_budgeted_engine_shares_one_deadline_and_reserves_cleanup():
    mod = api()
    assert hasattr(mod, 'BudgetedEngine'), 'bounded engine adapter missing'
    from scripts.performance.local_container_disposal import Creation
    now, calls = [0.0], []

    class Engine:
        def create(self, request, *, remaining):
            from scripts.performance.local_container_disposal import Container
            calls.append(('create', request, remaining))
            return Container(request.run, request.role, 'a' * 64 if request.role == 'source' else 'b' * 64, True)

        def remove(self, identity, *, remaining):
            calls.append(('remove', identity, remaining))

    engine = mod.BudgetedEngine(Engine(), clock=lambda: now[0], guard=lambda: None)
    engine.create(Creation('one', 'source'))
    now[0] = 94
    engine.create(Creation('one', 'destination'))
    assert engine.budget_for('one').started == 0
    assert calls[-1][-1] == 1
    now[0] = 95
    with pytest.raises(TimeoutError):
        engine.create(Creation('one', 'destination'))
    engine.remove('a' * 64)
    assert calls[-1] == ('remove', 'a' * 64, 25)
    now[0] = 120
    with pytest.raises(TimeoutError):
        engine.remove('a' * 64)


def test_late_absence_cannot_release_after_shared_deadline():
    mod = api()
    from scripts.performance.local_container_disposal import Container, Controller, Observation
    now = [0.0]

    class Engine:
        removed = False

        def create(self, request, *, remaining):
            return Container(request.run, request.role, ('a' if request.role == 'source' else 'b') * 64, True)

        def remove(self, identity, *, remaining):
            self.removed = True

        def observe(self, probe, *, remaining):
            if self.removed:
                now[0] = 121
            return Observation(probe, None if self.removed else probe.container)

    engine = mod.BudgetedEngine(Engine(), clock=lambda: now[0], guard=lambda: None)
    controller = Controller(engine)
    owners = controller.start('one')
    with pytest.raises(mod.Unconfirmed):
        controller.dispose(owners[0])
    assert controller.owned == owners
    assert owners[0].container_id in engine.pending


@pytest.mark.parametrize('cleanup_failure', [False, True])
def test_three_cell_sequence_composes_windows_worker_and_disposal(tmp_path, cleanup_failure):
    mod = api()
    from scripts.performance.local_container_disposal import Container, Observation
    from scripts.performance.local_container_sequence import Cell, Sequence
    from copy import deepcopy
    import hashlib
    now = [0.0]

    class Engine:
        count = 0

        def __init__(self):
            self.live = {}

        def create(self, request, *, remaining):
            self.count += 1
            owner = Container(request.run, request.role, f'{self.count:064x}', True)
            self.live[owner.container_id] = owner
            return owner

        def observe(self, probe, *, remaining):
            return Observation(probe, self.live.get(probe.container.container_id))

        def remove(self, identity, *, remaining):
            if cleanup_failure and self.live[identity].run == 'interrupted':
                raise OSError('injected cleanup failure')
            del self.live[identity]

    class WorkerBackend(Backend):
        def create_suspended(self, argv):
            self.request = Path(argv[-1])
            return super().create_suspended(argv)

        def resume(self, thread):
            value = json.loads(self.request.read_bytes())
            reply = {'request_sha256': hashlib.sha256(self.request.read_bytes()).hexdigest(),
                     'status': 'INVALID_PARTIAL' if value['interrupt'] else 'PASS_CONTROLLED_FINITE_PAIR',
                     'interrupted_after_ready': value['interrupt']}
            (self.request.parent / 'reply.json').write_text(json.dumps(reply))
            self.code, self.active = 0, 0

    raw_engine = Engine()
    engine = mod.BudgetedEngine(raw_engine, guard=lambda: None, clock=lambda: now[0])
    runner = mod.WindowsWorkload(tmp_path, budget_for=engine.budget_for, guard=lambda: None,
                                backend_factory=WorkerBackend,
                                sleep=lambda seconds: now.__setitem__(0, now[0] + seconds))
    sequence = Sequence(engine)
    config = json.loads(bound_plan(False).config_json)
    cells = []
    for name in ('normal', 'interrupted', 'fresh'):
        value = deepcopy(config)
        for role in ('source', 'destination'):
            value[role]['output'] = f'/evidence/{name}/{role}'
        cells.append(Cell(name, value, f'/configs/{name}.json', f'/controller/{name}'))
    if cleanup_failure:
        with pytest.raises(mod.Unconfirmed):
            sequence.run(cells, runner, original_disk_free_bytes=10 * 2**30)
        assert len(sequence.results) == 2
        assert len(sequence.controller.owned) == 2
        assert not (tmp_path / 'fresh').exists()
    else:
        results = sequence.run(cells, runner, original_disk_free_bytes=10 * 2**30)
        assert [row.status for row in results] == [
            'PASS_CONTROLLED_FINITE_PAIR', 'INVALID_PARTIAL', 'PASS_CONTROLLED_FINITE_PAIR']
        assert all(row.cleanup_confirmed for row in results)
        assert raw_engine.live == {}
    assert not runner.owner.owned


@pytest.mark.parametrize('stage', ['acquisition', 'loop'])
def test_deferred_or_exceptional_cancellation_cleans_exact_job(tmp_path, stage):
    mod = api()
    import signal
    now = [0.0]
    budget = mod.CellBudget(clock=lambda: now[0])
    acquisition_deferred = []

    class WorkerBackend(Backend):
        def create_suspended(self, argv):
            if stage == 'acquisition':
                handler = signal.getsignal(signal.SIGINT)
                # Invoke the installed handler as an ordinary callback; no OS signal.
                try:
                    handler(signal.SIGINT, None)
                    acquisition_deferred.append(True)
                except KeyboardInterrupt:
                    acquisition_deferred.append(False)
                    raise
            return super().create_suspended(argv)

        def terminate(self, *args):
            super().terminate(*args)
            self.code, self.active = 1, 0

    def sleep(seconds):
        if stage == 'loop':
            raise KeyboardInterrupt('synthetic interrupted wait')
        now[0] += seconds

    backend = WorkerBackend()
    runner = mod.WindowsWorkload(tmp_path, budget_for=lambda run: budget,
                                backend_factory=lambda: backend, guard=lambda: None, sleep=sleep)
    with pytest.raises(BaseException):
        runner(bound_plan(False))
    if stage == 'acquisition':
        assert acquisition_deferred == [True]
    assert not runner.owner.owned
    assert any(a[0] == 'kill' for a in backend.actions)
    report = json.loads((tmp_path / 'one' / 'supervision.json').read_text())
    assert report['status'] == 'INVALID_PARTIAL'


def test_empty_job_unsignalled_helper_retains_exact_handles_until_both_complete():
    mod = api()
    backend = Backend()
    owner = mod.WindowsOwner(['python', 'worker'], backend=backend, cancel=lambda: None)
    owner.start()
    handles = (owner.job, owner.process, owner.thread)
    backend.active = 0
    assert owner.observe() == (None, True)
    with pytest.raises(mod.Unconfirmed):
        owner.reap()
    assert (owner.job, owner.process, owner.thread) == handles
    # Later descendant activity still blocks release even after the leader exits.
    backend.code, backend.active = 1, 1
    assert owner.observe() == (1, True)
    with pytest.raises(mod.Unconfirmed):
        owner.reap()
    assert not any(a[0] == 'close' for a in backend.actions)
    backend.active = 0
    owner.reap()
    assert not owner.owned
    assert all(a[1:] == ('job', 'process', True)
               for a in backend.actions if a[0] == 'observe')
