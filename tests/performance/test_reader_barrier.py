import ast,hashlib,json,pathlib,sys
import pytest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[2]))
from scripts.performance import reader_output_limits as limits
from scripts.performance.reader_receipts import ReceiptPair
from scripts.performance.reader_barrier_v2 import ReceiptBarrier

def setup(tmp_path):
    command=tmp_path/'reader-command';command.mkdir();request=command/'request.json';request.write_bytes(b'{"work_deadline":90.0,"started":0.0}')
    identity=dict(run='r',source='/fixture',owner='a'*64,request_sha256=hashlib.sha256(request.read_bytes()).hexdigest())
    identity['owner']=hashlib.sha256(json.dumps(dict(run='r',source='/fixture',request_sha256=identity['request_sha256'],argv=('fixture-owner',),deadline=90.0),sort_keys=True,separators=(',',':')).encode()).hexdigest()
    pair=ReceiptPair(tmp_path,limits.live_completion_claim(limits.ClaimBook()),identity,checkpoint=lambda:None)
    pair.publish_closed('b'*64,post_permit=dict(schema='nbsr-reader-lifecycle-v1',run='r',source='/fixture',owner=identity['owner'],operation='clock-probes-only',anchor=0.0,deadline=90.0,capture_sha256='b'*64))
    barrier=ReceiptBarrier(tmp_path,'r','/fixture',lambda:None,owner_argv=('fixture-owner',),clock=lambda:0.0)
    return pair,barrier

@pytest.mark.parametrize('contradictory',[False,True])
def test_post_can_begin_closed_but_acceptance_waits_for_settlement(tmp_path,contradictory):
    pair,barrier=setup(tmp_path)
    assert barrier.wait_closed()['state']=='CLOSED_UNSETTLED'
    owner=dict(status='LOCAL_WORKER_COMPLETED',exit_code=0,leader_reaped=True,group_exit_observed=True,owned_handles=False,drain_failure=None,errors=[])
    raw=json.dumps(dict(owner,status='INVALID_PARTIAL') if contradictory else owner).encode();(tmp_path/'reader-command/supervision.json').write_bytes(raw)
    pair.publish_settled(valid=True,settlement_sha256=hashlib.sha256(raw).hexdigest())
    pair.publish_result(dict(status='LOCAL_READER_JOINED',joined=True,errors=[],identity=pair.identity,reader_value=owner))
    if contradictory:
        with pytest.raises(ValueError):barrier.wait_complete()
        assert barrier.failed
        return
    assert barrier.wait_complete()['joined'] is True
    p=tmp_path/'acquisition-result.json';old=p.read_bytes();p.write_bytes(old+b' ')
    with pytest.raises(ValueError):barrier.verify()
    p.write_bytes(old)
    with pytest.raises(ValueError):barrier.verify()

def test_wait_preserves_original_deadline_and_failure(tmp_path):
    _,barrier=setup(tmp_path);barrier.wait_closed()
    def expired():raise TimeoutError('original deadline')
    barrier.check=expired
    with pytest.raises(TimeoutError):barrier.wait_complete()
    assert barrier.failed



@pytest.mark.parametrize('raw',[b'{"x":1,"x":2}',b'{"x":NaN}',b'{"x":Infinity}'])
def test_protocol_json_rejects_ambiguous_values(raw):
    from scripts.performance.reader_receipts import decode
    with pytest.raises(ValueError):decode(raw)

def test_invalid_deadline_cannot_create_barrier_identity(tmp_path):
    _,barrier=setup(tmp_path)
    (tmp_path/'reader-command/request.json').write_bytes(b'{"work_deadline":1e999,"started":0}')
    with pytest.raises(ValueError):barrier.wait_closed()
    assert barrier.failed

def test_cross_process_cancel_is_irreversible(tmp_path):
    _,barrier=setup(tmp_path);barrier.wait_closed()
    barrier.cancelled=lambda:True
    with pytest.raises(ValueError):barrier.verify()
    barrier.cancelled=lambda:False
    with pytest.raises(ValueError):barrier.verify()

def test_post_permit_deadline_cannot_be_extended_by_outer_window(tmp_path):
    _,barrier=setup(tmp_path);barrier.wait_closed()
    barrier.clock=lambda:90.0
    with pytest.raises(TimeoutError):barrier.verify()
    barrier.clock=lambda:1.0
    with pytest.raises(ValueError):barrier.verify()

def test_actual_post_window_caps_bounded_command_to_original_permit(tmp_path):
    import types
    _,barrier=setup(tmp_path);barrier.wait_closed()
    outer=types.SimpleNamespace(phase_end=120.0,end=150.0,check_work=lambda:None,post_budget=lambda:30.0)
    limited=barrier.post_window(outer)
    assert limited.phase_end==limited.end==90.0
    barrier.clock=lambda:85.0
    assert limited.post_budget()==5.0
    barrier.clock=lambda:90.0
    with pytest.raises(TimeoutError):limited.check_work()

@pytest.mark.parametrize('where',['barrier','window','budget','clock','cancel'])
def test_transient_callbacks_fail_permanently(tmp_path,where):
    import types
    _,barrier=setup(tmp_path);barrier.wait_closed()
    outer=types.SimpleNamespace(phase_end=120.0,end=150.0,check_work=lambda:None,post_budget=lambda:30.0)
    window=barrier.post_window(outer)
    def failure():raise RuntimeError('transient callback')
    if where=='barrier':barrier.check=failure;call=barrier._check;restore=lambda:setattr(barrier,'check',lambda:None)
    elif where=='window':outer.check_work=failure;call=window.check_work;restore=lambda:setattr(outer,'check_work',lambda:None)
    elif where=='budget':outer.post_budget=failure;call=window.post_budget;restore=lambda:setattr(outer,'post_budget',lambda:30.0)
    elif where=='clock':barrier.clock=failure;call=barrier._check;restore=lambda:setattr(barrier,'clock',lambda:0.0)
    else:barrier.cancelled=failure;call=barrier._check;restore=lambda:setattr(barrier,'cancelled',lambda:False)
    with pytest.raises(RuntimeError):call()
    restore()
    with pytest.raises(ValueError):barrier.verify()
