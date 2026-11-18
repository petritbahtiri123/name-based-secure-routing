"""Offline composition: real parser/acquisition/lifecycle/receipts; injected owner and POST evidence.
No native child, transport, listener, VM, or scientific benchmark qualification.
"""
import base64,hashlib,json,threading,time
import pytest
from test_reader_capture_adapter import fixture
from scripts.performance import reader_output_limits as limits
from scripts.performance.reader_acquisition import Acquisition
from lab import bridge
from scripts.performance.reader_capture import FinalCapture
from scripts.performance.reader_launcher import ReaderLauncher
from scripts.performance.reader_barrier_v2 import ReceiptBarrier

@pytest.mark.parametrize('bad',[None,'post-over-90s','persisted-capture','aggregate-failed'])
def test_composed_reader_settlement_post_acceptance(tmp_path,bad):
    live=tmp_path/'live-lab';live.mkdir();command=live/'reader-command';command.mkdir();inbox=live/'inbox';inbox.mkdir()
    whole,grants=limits.live_partition_claims(limits.ClaimBook())
    # Repository bridge is real; private producer accounting is not promoted here.
    consumer=bridge.FramedBridge(live/'capture',inbox,'r','/fixture')
    pump=bridge.FrameLogPump(consumer,131072)
    f=fixture();raw=f['origin_line']()+f['line'](f['progress']())+f['line'](f['progress'](2))+f['line'](f['final']())
    frames=[dict(schema='nbsr-lab-reader-start-v1',run='r',source='/fixture',state='waiting-for-source',cadence_seconds=5,lifetime_seconds=80,wire_budget=131072),dict(schema='nbsr-lab-prefix-v1',run='r',source='/fixture',sequence=1,file_identity=[1,2],prefix=base64.b64encode(raw).decode()),dict(schema='nbsr-lab-reader-ended-v1',run='r',reason='source-final-observed',observations=1)]
    log=command/'stdout.log';log.write_bytes(b''.join(f['line'](row) for row in frames))
    anchor=time.monotonic();deadline=anchor+5
    request=command/'request.json';request.write_text(json.dumps(dict(started=anchor,work_deadline=deadline,output=str(command))))
    class Native:
        def __init__(self):self.owned=False;self.observed=self.reaped=0
        def observe(self):
            assert self.owned
            self.observed+=1
            return 0,False
        argv=('injected-reader',);cancelled=False;killed=False;drain_failure=None
        def start(self):
            self.owned=True;self.started=self.assigned=True;self.job=object();self.process=object();self.thread=object()
        def reap(self):
            assert self.owned
            self.reaped+=1;self.owned=False;self.job=self.process=self.thread=None
    native=Native();native.deadline=deadline
    def budget():
        if whole.failed or any(c.failed for c in grants.values()):raise ValueError('aggregate failed')
    holder={};gate=threading.Event()
    def reader():
        assert gate.wait(1)
        launcher=holder['launcher'];launcher.prepare(native,request,anchor,deadline)
        native.start();launcher.checkpoint(native)
        assert launcher.consume(native) is True
        # Injected owner outcome, not a native supervisor or command-wrapper proof.
        result=dict(status='LOCAL_WORKER_COMPLETED',exit_code=0,leader_reaped=True,
                    group_exit_observed=True,owned_handles=native.owned,
                    drain_failure=native.drain_failure,errors=[])
        encoded=json.dumps(result).encode();(command/'supervision.json').write_bytes(encoded)
        launcher.settle(hashlib.sha256(encoded).hexdigest())
        return result
    def poll(*,final):
        pump.poll(log)
        if final:consumer.bridge.finish()
        return {'ready':consumer.started}
    acq=Acquisition(reader,poll,interval=.01,whole=5,ready_budget=1)
    final_capture=FinalCapture(acq,consumer,pump,run='r',source='/fixture',wire_cap=131072,log_path=log)
    launcher=ReaderLauncher(run='r',source='/fixture',directory=live,claim=grants['completion_shared'],capture=final_capture,clock=time.monotonic,budget_check=budget)
    holder['launcher']=launcher;acq.start(wait_ready=False);gate.set();result=acq.finish()
    assert result['status']=='LOCAL_READER_JOINED',result
    launcher.finish(result)
    barrier=ReceiptBarrier(live,'r','/fixture',lambda:None,owner_argv=native.argv,clock=time.monotonic)
    barrier.wait_closed();barrier.wait_complete();barrier.verify()
    path=tmp_path/'cells/baseline8/CALIBRATION.json';path.parent.mkdir(parents=True)
    path.write_text(json.dumps(dict(reader_lifecycle=barrier.post_binding,all_samples_retained=True,span_ns=90000000001 if bad=='post-over-90s' else 90000000000)))
    if bad=='persisted-capture':log.write_bytes(log.read_bytes()+b'x')
    if bad=='aggregate-failed':limits.mark_unknown(whole,'injected-late-overflow')
    if bad:
        with pytest.raises((ValueError,RuntimeError)):launcher.wait_post(path)
        assert launcher.failed and launcher.lifecycle.state=='INVALID'
    else:
        launcher.wait_post(path);launcher.verify_post()
        accepted=launcher.lifecycle.accept()
        assert accepted['lifecycle_complete'] is True
        assert accepted['campaign_validity']=='REQUIRES_OTHER_GATES'
    assert native.observed==native.reaped==1
    assert whole.reserved_bytes==2492*1024
