"""Actual owner methods with injected OS backend
no native child or publisher."""
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.performance.receiver_observed_owner import ObservedReceiverOwner
from scripts.performance.viewer_owner_observation import ObservationSlot


class Backend:
    def __init__(self):
        self.code, self.active = None, 1
        self.observations = 0
        self.closed = []
        self.terminated = False

    def create_job(self):
        return object()

    def create_suspended(self, argv):
        return object(), object()

    def assign(self, job, process):
        pass

    def resume(self, thread):
        pass

    def observe(self, *args):
        self.observations += 1
        return self.code, self.active

    def close(self, handle):
        self.closed.append(handle)

    def terminate(self, *args):
        self.terminated = True

    def member_pids(self, job):
        return [17]


def make():
    clock = [11.]
    slot = ObservationSlot(('run', 'request', 'ready'), anchor=10., deadline=125.)
    backend = Backend()
    owner = ObservedReceiverOwner(('fixture-only',), backend=backend, cancel=lambda: None,
        deadline=183., clock=lambda: clock[0], observation=slot)
    owner.start()
    return owner, backend, slot, clock


def test_observe_answers_without_extra_native_call():
    owner, backend, slot, _ = make()
    seq = slot.request(now=11.)
    assert owner.observe() == (None, True)
    assert backend.observations == 1
    reply = slot.take(seq, now=11.)
    slot.revalidate(reply, now=11.)


def test_terminal_observation_revokes_before_reap():
    owner, backend, slot, _ = make()
    slot.request(now=11.)
    backend.code, backend.active = 0, 0
    assert owner.observe() == (0, False)
    with pytest.raises(ValueError):
        slot.request(now=11.)
    owner.reap()
    assert not owner.owned and len(backend.closed) == 3


@pytest.mark.parametrize('signal', ['INT', 'TERM', 'KILL'])
def test_signal_revokes_before_original_cleanup(signal):
    owner, backend, slot, _ = make()
    seq = slot.request(now=11.)
    owner.observe()
    reply = slot.take(seq, now=11.)
    owner.signal(signal)
    with pytest.raises(ValueError):
        slot.revalidate(reply, now=11.)
    assert owner.killed if signal == 'KILL' else owner.cancelled


def test_viewer_expiry_does_not_shorten_native_deadline():
    owner, backend, slot, clock = make()
    slot.request(now=11.)
    clock[0] = 126.
    assert owner.observe() == (None, True)
    assert owner.observation_error == 'ValueError'
    assert not backend.terminated and owner.drain_failure is None


def test_foreign_thread_cannot_observe_owned_handles():
    owner, backend, slot, _ = make()
    errors = []
    def other():
        try:
            owner.observe()
        except RuntimeError as error:
            errors.append(str(error))
    thread = threading.Thread(target=other)
    thread.start()
    thread.join(1.)
    assert not thread.is_alive() and errors
    assert backend.observations == 0
    with pytest.raises(ValueError):
        slot.request(now=11.)


def test_exited_leader_with_draining_descendant_is_not_attachable():
    owner, backend, slot, _ = make()
    seq = slot.request(now=11.)
    backend.code = 0
    assert owner.observe() == (None, True)
    with pytest.raises(ValueError):
        slot.take(seq, now=11.)


def test_existing_retain_owner_accepts_exact_adapter_once():
    owner, _, _, _ = make()
    current = SimpleNamespace(thread=threading.current_thread(), owner=None, viewer_lock=threading.Lock(), viewer_revoked=False)
    source = Path(__file__).with_name('fixtures') / 'receiver_retain_owner.py.snapshot'
    namespace = {'_CURRENT': current}
    exec(compile(source.read_bytes(), str(source), 'exec'), namespace)
    namespace['retain_owner'](owner)
    assert current.owner is owner
    with pytest.raises(RuntimeError, match='owner binding'):
        namespace['retain_owner'](owner)


def test_request_arriving_during_native_observe_waits_for_next_sample():
    owner, backend, slot, clock = make()
    original = backend.observe
    requested = []

    def observe(*args):
        result = original(*args)
        if not requested:
            clock[0] = 12.
            requested.append(slot.request(now=12.))
        return result

    backend.observe = observe
    owner.observe()
    assert slot.pending(now=12.) == requested[0]
    owner.observe()
    assert slot.take(requested[0], now=12.).observed_at == 12.

@pytest.mark.parametrize('stage', ['create_job', 'create_suspended', 'assign', 'resume'])
def test_start_failure_revokes_and_retains_handles_for_original_cleanup(stage):
    backend = Backend()
    slot = ObservationSlot(('run', 'request', 'ready'), anchor=10., deadline=125.)
    # A fresh isolated backend never launches a native child.
    owner = ObservedReceiverOwner(('fixture-only',), backend=backend, cancel=lambda: None,
        deadline=183., clock=lambda: 11., observation=slot)
    original = getattr(backend, stage)
    def fail(*args):
        raise OSError(stage)
    setattr(backend, stage, fail)
    with pytest.raises(OSError, match=stage):
        owner.start()
    with pytest.raises(ValueError):
        slot.request(now=11.)
    setattr(backend, stage, original)
    if owner.owned:
        owner.signal('KILL')
        backend.code, backend.active = 1, 0
        owner.reap()
    assert not owner.owned


def test_native_observe_failure_revokes_before_termination_side_effect():
    owner, backend, slot, _ = make()
    def fail(*args):
        raise OSError('native observation')
    def terminate(*args):
        with pytest.raises(ValueError):
            slot.request(now=11.)
        backend.terminated = True
    backend.observe = fail
    backend.terminate = terminate
    with pytest.raises(OSError, match='native observation'):
        owner.observe()
    assert backend.terminated and owner.drain_failure == 'OSError'


@pytest.mark.parametrize('signal', ['INT', 'TERM', 'KILL'])
def test_revocation_precedes_backend_or_cancel_callback(signal):
    owner, backend, slot, _ = make()
    calls = []
    def side_effect(*args):
        with pytest.raises(ValueError):
            slot.request(now=11.)
        calls.append(signal)
    owner.cancel = side_effect
    backend.terminate = side_effect
    owner.signal(signal)
    assert calls == [signal]


def test_reap_revokes_before_observe_and_close_callbacks():
    owner, backend, slot, _ = make()
    backend.code, backend.active = 0, 0
    original_observe, original_close = backend.observe, backend.close
    def observe(*args):
        with pytest.raises(ValueError):
            slot.request(now=11.)
        return original_observe(*args)
    def close(handle):
        with pytest.raises(ValueError):
            slot.request(now=11.)
        original_close(handle)
    backend.observe, backend.close = observe, close
    owner.reap()
    assert not owner.owned and len(backend.closed) == 3


def bounded_fixture(tmp_path, monkeypatch, supervise):
    """Actual run body/finally; injected admission/accounting and supervisor.

    No activate, child, native API, receiver worker or network is executed.
    """
    import ctypes
    import json
    import math
    import sys
    import time
    from scripts.performance.reader_windows_drain import DrainingOwner

    root = tmp_path / 'candidate'
    cell = root / 'cells' / 'baseline8'
    cell.mkdir(parents=True)
    (root / 'live-lab').mkdir()
    (cell / 'LOCAL-ADMISSION.json').write_text(json.dumps({'retained_bytes': 6739946464}))
    backend = Backend()
    backend.exit_observations = []
    current = SimpleNamespace(thread=threading.current_thread(), owner=None, viewer_lock=threading.Lock(), viewer_revoked=False)
    retain_path = Path(__file__).with_name('fixtures') / 'receiver_retain_owner.py.snapshot'
    receiver = SimpleNamespace(__file__=str(root / 'finite_receiver.py'), _CURRENT=current)
    scope = receiver.__dict__
    exec(compile(retain_path.read_bytes(), str(retain_path), 'exec'), scope)
    effects = []
    for name, module in {
        'activate': SimpleNamespace(activate=lambda: effects.append('activate')),
        'draining_owner': SimpleNamespace(DrainingOwner=DrainingOwner),
        'diagnostic_backend': SimpleNamespace(DiagnosticBackend=lambda: backend),
        'baseline_watchdog': SimpleNamespace(supervise=supervise),
        'finite_receiver': receiver,
    }.items():
        monkeypatch.setitem(sys.modules, name, module)
    class Book:
        def __init__(self):
            effects.append('claim-book')
    def claims(book):
        return {name: SimpleNamespace(partition='live', purpose=name, maximum_bytes=65536, reserved_bytes=0)
                for name in ('request.json', 'job-exit-observations.json', 'job-drain.json', 'supervision.json')}
    def memory(value):
        value._obj.available = value._obj.page_available = 4 * 1024 ** 3
        return True
    class Memory(ctypes.Structure):
        _fields_ = [('length', ctypes.c_ulong), ('available', ctypes.c_ulonglong), ('page_available', ctypes.c_ulonglong)]
    fake_ctypes = SimpleNamespace(sizeof=ctypes.sizeof, byref=ctypes.byref,
        windll=SimpleNamespace(kernel32=SimpleNamespace(GlobalMemoryStatusEx=memory)))
    counts = {'task': 6739946464, 'artifacts': 0, 'output': 0}
    ns = dict(__file__=str(cell / 'bounded.py'), pathlib=__import__('pathlib'),
        math=math, json=json, sys=sys, time=time, ctypes=fake_ctypes, MemoryStatus=Memory,
        COORDINATOR=185, WRAPPER=195, FINALIZATION=180, ClaimBook=Book,
        output_limits=SimpleNamespace(live_receiver_claims=claims),
        resource_boundary=SimpleNamespace(check=lambda **kw: counts.copy()),
        _receiver_arguments=lambda argv: None, _request_arguments=lambda *args: None,
        _request_window=lambda *args: None,
        _write_required=lambda path, claim, value: path.write_text(json.dumps(value)),
        mark_unknown=lambda *args: effects.append('unknown'), OutputLimitError=RuntimeError,
        purpose_for_path=lambda path: path)
    source = Path(__file__).with_name('fixtures') / 'receiver_bounded_run.py.snapshot'
    exec(compile(source.read_bytes(), str(source), 'exec'), ns)
    anchor = time.monotonic()
    slot = ObservationSlot(('fixture', 'request', 'ready'), anchor=anchor, deadline=anchor + 115.)
    return ns['run'], root / 'live-lab' / 'receiver-command', anchor, slot, backend, current, effects


@pytest.mark.parametrize('observed', [False, True])
def test_actual_run_retains_same_owner_and_finally_cleans_on_monitor_thread(tmp_path, monkeypatch, observed):
    seen = []
    def supervise(owner, **kwargs):
        seen.append(owner)
        owner.start()
        # Simulate watchdog unwind with retained handles: run's genuine finally cleans them.
        raise OSError('supervisor unwind')
    run, output, anchor, slot, backend, current, _ = bounded_fixture(tmp_path, monkeypatch, supervise)
    def terminate(*args):
        if observed:
            with pytest.raises(ValueError):
                slot.request(now=anchor + .01)
        backend.code, backend.active = 1, 0
    backend.terminate = terminate
    with pytest.raises(OSError, match='supervisor unwind'):
        run(['fixture-only'], output, work=170, trial_anchor=anchor,
            receiver_observation=slot if observed else None)
    assert current.owner is seen[0]
    assert isinstance(current.owner, ObservedReceiverOwner) is observed
    assert not current.owner.owned and len(backend.closed) == 3
    assert (output / 'supervision.json').exists()


def test_actual_run_rejects_wrong_path_slot_before_claims(tmp_path, monkeypatch):
    run, output, anchor, slot, _, _, effects = bounded_fixture(tmp_path, monkeypatch, lambda *a, **kw: None)
    with pytest.raises(ValueError, match='receiver-only'):
        run(['fixture-only'], output.parent.parent / 'cells' / 'baseline8' / 'ordinary',
            receiver_observation=slot)
    assert effects == []


def test_actual_run_binding_rejection_precedes_start_or_native_allocation(tmp_path, monkeypatch):
    run, output, anchor, slot, backend, current, _ = bounded_fixture(tmp_path, monkeypatch, lambda *a, **kw: pytest.fail('supervise reached'))
    current.owner = object()
    backend.create_job = lambda: pytest.fail('native allocation reached')
    with pytest.raises(RuntimeError, match='owner binding'):
        run(['fixture-only'], output, work=170, trial_anchor=anchor, receiver_observation=slot)
    assert not backend.closed
    with pytest.raises(ValueError):
        slot.request(now=anchor + .01)


@pytest.mark.parametrize('stage', ['resume', 'observe'])
def test_actual_run_failure_retains_then_cleans_original_owner(tmp_path, monkeypatch, stage):
    def supervise(owner, **kwargs):
        owner.start()
        owner.observe()
    run, output, anchor, slot, backend, current, _ = bounded_fixture(tmp_path, monkeypatch, supervise)
    original = getattr(backend, stage)
    def once(*args):
        setattr(backend, stage, original)
        raise OSError('injected ' + stage)
    setattr(backend, stage, once)
    def terminate(*args):
        with pytest.raises(ValueError):
            slot.request(now=anchor + .01)
        backend.code, backend.active = 1, 0
    backend.terminate = terminate
    with pytest.raises(OSError, match='injected'):
        run(['fixture-only'], output, work=170, trial_anchor=anchor, receiver_observation=slot)
    assert current.owner is not None and not current.owner.owned
    assert len(backend.closed) == 3


def test_actual_run_success_binds_observes_then_reaps_original_owner(tmp_path, monkeypatch):
    def supervise(owner, **kwargs):
        owner.start()
        kwargs['guard']()
        seq = slot.request(now=__import__('time').monotonic())
        owner.observe()
        reply = slot.take(seq, now=__import__('time').monotonic())
        slot.revalidate(reply, now=__import__('time').monotonic())
        backend.code, backend.active = 0, 0
        owner.reap()
        return {'status': 'LOCAL_WORKER_COMPLETED'}
    run, output, anchor, slot, backend, current, _ = bounded_fixture(tmp_path, monkeypatch, supervise)
    result = run(['fixture-only'], output, work=170, trial_anchor=anchor, receiver_observation=slot)
    assert result == {'status': 'LOCAL_WORKER_COMPLETED', 'drain_failure': None, 'owned_handles': False}
    assert current.owner is not None and not current.owner.owned
    with pytest.raises(ValueError):
        slot.request(now=__import__('time').monotonic())


def test_receiver_binding_is_one_shot_and_exact():
    slot = ObservationSlot(('run', 'request', 'ready'), anchor=10., deadline=125.)
    slot.bind_receiver(('run', 'request', 'ready'), anchor=10., deadline=125., now=11.)
    with pytest.raises(ValueError):
        slot.bind_receiver(('run', 'request', 'ready'), anchor=10., deadline=125., now=11.)
    with pytest.raises(ValueError):
        slot.request(now=11.)


@pytest.mark.parametrize('identity,anchor,deadline', [
    (('other', 'request', 'ready'), 10., 125.),
    (('run', 'other', 'ready'), 10., 125.),
    (('run', 'request', 'other'), 10., 125.),
    (('run', 'request', 'ready'), 11., 125.),
    (('run', 'request', 'ready'), 10., 126.),
    (('run', 'request', 'ready'), True, 125.),
])
def test_receiver_binding_mismatch_is_irreversible(identity, anchor, deadline):
    slot = ObservationSlot(('run', 'request', 'ready'), anchor=10., deadline=125.)
    with pytest.raises(ValueError):
        slot.bind_receiver(identity, anchor=anchor, deadline=deadline, now=11.)
    with pytest.raises(ValueError):
        slot.bind_receiver(('run', 'request', 'ready'), anchor=10., deadline=125., now=11.)


def test_receiver_binding_rejects_previously_used_slot():
    slot = ObservationSlot(('run', 'request', 'ready'), anchor=10., deadline=125.)
    slot.request(now=11.)
    with pytest.raises(ValueError):
        slot.bind_receiver(('run', 'request', 'ready'), anchor=10., deadline=125., now=11.)


@pytest.mark.parametrize('now', [True, float('nan'), float('inf'), 9., 125.])
def test_receiver_binding_rejects_uncertain_or_expired_clock(now):
    slot = ObservationSlot(('run', 'request', 'ready'), anchor=10., deadline=125.)
    with pytest.raises(ValueError):
        slot.bind_receiver(('run', 'request', 'ready'), anchor=10., deadline=125., now=now)
    with pytest.raises(ValueError):
        slot.request(now=11.)


def test_bound_slot_observation_preserves_original_identity():
    slot = ObservationSlot(('run', 'request', 'ready'), anchor=10., deadline=125.)
    slot.bind_receiver(('run', 'request', 'ready'), anchor=10., deadline=125., now=11.)
    seq = slot.request(now=11.)
    slot.answer(seq, owned=True, now=11.)
    assert slot.take(seq, now=11.).identity == ('run', 'request', 'ready')


def test_disabled_owner_install_waits_for_next_native_sample():
    backend = Backend()
    owner = ObservedReceiverOwner(('fixture-only',), backend=backend, cancel=lambda: None,
        deadline=183., clock=lambda: 11., observation=None)
    owner.start()
    slot = ObservationSlot(('run', 'request', 'ready'), anchor=10., deadline=125.)
    slot.bind_receiver(('run', 'request', 'ready'), anchor=10., deadline=125., now=11.)
    original = backend.observe
    def during(*args):
        owner.install_observation(slot)
        slot.request(now=11.)
        backend.observe = original
        return original(*args)
    backend.observe = during
    owner.observe()
    assert slot.pending(now=11.) == 1
    owner.observe()
    assert slot.take(1, now=11.).identity[0] == 'run'


@pytest.mark.parametrize('action', ['terminal', 'INT', 'KILL', 'reap'])
def test_disabled_owner_terminal_prevents_late_install(action):
    backend = Backend()
    owner = ObservedReceiverOwner(('fixture-only',), backend=backend, cancel=lambda: None,
        deadline=183., clock=lambda: 11., observation=None)
    owner.start()
    if action in ('terminal', 'reap'):
        backend.code, backend.active = 0, 0
        owner.reap() if action == 'reap' else owner.observe()
    else:
        owner.signal(action)
    slot = ObservationSlot(('run', 'request', 'ready'), anchor=10., deadline=125.)
    slot.bind_receiver(('run', 'request', 'ready'), anchor=10., deadline=125., now=11.)
    with pytest.raises(ValueError):
        owner.install_observation(slot)


def post_ready_fixture(tmp_path, monkeypatch, *, late=False):
    import json
    import sys
    import time
    root = tmp_path / 'post-ready'
    directory = root / 'live-lab' / 'receiver-command'
    anchor = time.monotonic() - (120 if late else 0)
    ns = dict(_CURRENT=None, ROOT=root, RUN='fixture', time=time, pathlib=__import__('pathlib'), sys=sys,
              require_native_qualification=lambda: None, _claims=lambda: {})
    source = Path(__file__).with_name('fixtures') / 'receiver_owner.py.snapshot'
    exec(compile(source.read_bytes(), str(source), 'exec'), ns)
    receiver = ns['Owner'](anchor, anchor + 175)
    backend = Backend()
    native = ObservedReceiverOwner((sys.executable, '-B', str(root / 'cells' / 'baseline8' / 'bounded.py'),
        'worker', str(directory / 'request.json')), observation=None, backend=backend,
        cancel=lambda: None, deadline=anchor + 173)
    receiver.owner = native
    def boot():
        directory.mkdir(parents=True)
        native.start()
        request = dict(argv=[sys.executable, '-B', str(root / 'finite_receiver.py'), 'worker',
                            str(directory / 'request.json')], output=str(directory), started=anchor,
                       trial_anchor=anchor, work_deadline=anchor + 170, cleanup_deadline=anchor + 175)
        (directory / 'request.json').write_text(json.dumps(request))
        (directory / 'ready.json').write_text(json.dumps(dict(run='fixture', deadline=anchor + 175, port=8766)))
    receiver.thread = SimpleNamespace(start=boot, is_alive=lambda: False, ident=threading.get_ident())
    ns['_read'] = lambda directory, name, claims: json.loads((directory / name).read_bytes())
    def publish(directory, name, value, claims):
        with pytest.raises(ValueError):
            receiver.viewer_attachment.slot.request(now=time.monotonic())
        (directory / name).write_text(json.dumps(value))
    ns['_publish'] = publish
    def joined(timeout):
        backend.code, backend.active = 0, 0
        native.reap()
        receiver.result = {'status': 'LOCAL_WORKER_COMPLETED'}
        (directory / 'ended.json').write_text(json.dumps(dict(run='fixture', deadline=anchor + 175,
            sqlite_closed=True, success=True, final=False)))
    receiver.thread.join = joined
    return receiver, native, backend, directory


def test_actual_start_branch_installs_after_real_bounded_ipc_then_finish_revokes(tmp_path, monkeypatch):
    import time
    receiver, native, backend, directory = post_ready_fixture(tmp_path, monkeypatch)
    receiver.start()
    attachment = receiver.viewer_attachment
    seq = attachment.slot.request(now=time.monotonic())
    native.observe()
    reply = attachment.slot.take(seq, now=time.monotonic())
    attachment.verify()
    assert reply.identity[0] == 'fixture'
    assert receiver.finish(require_final=False)['joined'] is True
    assert not native.owned and len(backend.closed) == 3


def test_actual_start_late_ready_continues_without_visualization(tmp_path, monkeypatch):
    receiver, native, backend, _ = post_ready_fixture(tmp_path, monkeypatch, late=True)
    receiver.start()
    assert receiver.viewer_error == 'ValueError'
    assert not hasattr(receiver, 'viewer_attachment')
    assert native.owned and not backend.terminated and not native.cancelled


def test_actual_abort_revokes_before_cancel_file(tmp_path, monkeypatch):
    import time
    receiver, native, _, directory = post_ready_fixture(tmp_path, monkeypatch)
    receiver.start()
    receiver.abort()
    assert (directory / 'cancel').exists()
    with pytest.raises(ValueError):
        receiver.viewer_attachment.slot.request(now=time.monotonic())
    assert native.owned  # Abort requests existing cancellation, never reaps here.


@pytest.mark.parametrize('name', ['request.json', 'ready.json'])
def test_post_ready_mutation_invalidates_permanently(tmp_path, monkeypatch, name):
    import time
    receiver, _, _, directory = post_ready_fixture(tmp_path, monkeypatch)
    receiver.start()
    binding = receiver.viewer_attachment
    path = directory / name
    raw = path.read_bytes()
    path.write_bytes(raw + b' ')
    with pytest.raises(ValueError):
        binding.verify()
    path.write_bytes(raw)
    with pytest.raises(ValueError):
        binding.verify()
    with pytest.raises(ValueError):
        binding.slot.request(now=time.monotonic())


def test_cross_thread_install_during_observe_uses_next_generation():
    backend = Backend()
    owner = ObservedReceiverOwner(('fixture-only',), backend=backend, cancel=lambda: None,
        deadline=183., clock=lambda: 11., observation=None)
    owner.start()
    slot = ObservationSlot(('run', 'request', 'ready'), anchor=10., deadline=125.)
    slot.bind_receiver(('run', 'request', 'ready'), anchor=10., deadline=125., now=11.)
    entered, installed = threading.Event(), threading.Event()
    errors = []
    def install():
        try:
            assert entered.wait(1.)
            owner.install_observation(slot)
            slot.request(now=11.)
        except BaseException as error:
            errors.append(error)
        finally:
            installed.set()
    thread = threading.Thread(target=install)
    original = backend.observe
    def observe(*args):
        entered.set()
        assert installed.wait(1.)
        backend.observe = original
        return original(*args)
    backend.observe = observe
    thread.start()
    owner.observe()
    thread.join(1.)
    assert not thread.is_alive() and not errors
    assert slot.pending(now=11.) == 1
    owner.observe()
    assert slot.take(1, now=11.) is not None


def test_disable_during_observation_cannot_publish_reply():
    owner, backend, slot, _ = make()
    slot.request(now=11.)
    original = backend.observe
    def observe(*args):
        owner.disable_observation()
        return original(*args)
    backend.observe = observe
    owner.observe()
    with pytest.raises(ValueError):
        slot.take(1, now=11.)


@pytest.mark.parametrize('bad', ['duplicate', 'wrong_run', 'oversize'])
def test_post_ready_bad_records_never_enable_observation(tmp_path, monkeypatch, bad):
    import json
    receiver, native, backend, directory = post_ready_fixture(tmp_path, monkeypatch)
    boot = receiver.thread.start
    def boot_bad():
        boot()
        path = directory / 'ready.json'
        if bad == 'duplicate':
            path.write_bytes(path.read_bytes()[:-1] + b', "port": 8766}')
        elif bad == 'wrong_run':
            value = json.loads(path.read_bytes())
            value['run'] = 'wrong'
            path.write_text(json.dumps(value))
        else:
            path.write_bytes(path.read_bytes() + b' ' * 1024)
    receiver.thread.start = boot_bad
    receiver.start()
    assert hasattr(receiver, 'viewer_error') and not hasattr(receiver, 'viewer_attachment')
    assert native.owned and not backend.terminated


@pytest.mark.parametrize('action', ['abort', 'finish'])
def test_actual_stop_before_retain_prevents_ready_handoff(tmp_path, monkeypatch, action):
    receiver, native, backend, directory = post_ready_fixture(tmp_path, monkeypatch)
    boot = receiver.thread.start
    def stopped_boot():
        boot()
        receiver.owner = None
        if action == 'abort':
            receiver.abort()
        else:
            receiver.thread.join = lambda timeout: None
            scope = receiver.finish.__func__.__globals__
            scope['_publish'] = lambda *args: None
            with pytest.raises(RuntimeError, match='cleanup UNKNOWN'):
                receiver.finish(require_final=False)
        source = Path(__file__).with_name('fixtures') / 'receiver_retain_owner.py.snapshot'
        ns = {'_CURRENT': receiver}
        exec(compile(source.read_bytes(), str(source), 'exec'), ns)
        ns['retain_owner'](native)
    receiver.thread.start = stopped_boot
    receiver.start()
    assert receiver.viewer_revoked and not hasattr(receiver, 'viewer_attachment')
    assert receiver.owner is native and native.owned and not backend.terminated
    slot = ObservationSlot(('run', 'request', 'ready'), anchor=10., deadline=125.)
    slot.bind_receiver(('run', 'request', 'ready'), anchor=10., deadline=125., now=11.)
    with pytest.raises(ValueError):
        native.install_observation(slot)


def test_install_failure_revokes_old_and_supplied_slot_and_prevents_retry():
    owner, _, old, _ = make()
    new = ObservationSlot(('run', 'request', 'ready'), anchor=10., deadline=125.)
    new.bind_receiver(('run', 'request', 'ready'), anchor=10., deadline=125., now=11.)
    with pytest.raises(ValueError):
        owner.install_observation(new)
    for slot in (old, new):
        with pytest.raises(ValueError):
            slot.request(now=11.)
    fresh = ObservationSlot(('run', 'request', 'ready'), anchor=10., deadline=125.)
    fresh.bind_receiver(('run', 'request', 'ready'), anchor=10., deadline=125., now=11.)
    with pytest.raises(ValueError):
        owner.install_observation(fresh)


def test_abort_between_ready_read_and_install_is_irreversible(tmp_path, monkeypatch):
    from scripts.performance.receiver_post_ready import PostReady
    receiver, native, _, _ = post_ready_fixture(tmp_path, monkeypatch)
    original = PostReady.verify
    def abort_first(binding):
        receiver.abort()
        return original(binding)
    monkeypatch.setattr(PostReady, 'verify', abort_first)
    receiver.start()
    assert receiver.viewer_revoked and not hasattr(receiver, 'viewer_attachment')
    assert native.owned


def test_cancel_during_post_ready_reread_cannot_return_success(tmp_path, monkeypatch):
    receiver, native, _, _ = post_ready_fixture(tmp_path, monkeypatch)
    receiver.start()
    binding = receiver.viewer_attachment
    original = binding._read
    def cancel_after_read(name, cap):
        value = original(name, cap)
        receiver.abort()
        return value
    monkeypatch.setattr(binding, '_read', cancel_after_read)
    with pytest.raises(ValueError, match='no longer installed'):
        binding.verify()
    assert binding.failed and native.owned
    monkeypatch.setattr(binding, '_read', original)
    with pytest.raises(ValueError):
        binding.verify()
