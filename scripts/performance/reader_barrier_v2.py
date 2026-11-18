"""Read-only bounded consumer for v2 receipts, tied to the original clock window."""
import hashlib,json,pathlib,time,math
from scripts.performance.reader_receipts import ReceiptPair,decode

class ReceiptBarrier:
    def __init__(self,directory,run,source,check,*,owner_argv,cancelled=lambda:False,clock=time.monotonic,sleep=time.sleep):
        self.directory=pathlib.Path(directory);self.run=run;self.source=source
        if type(owner_argv) is not tuple or not owner_argv or any(type(x) is not str or not x for x in owner_argv):raise ValueError('exact launcher argv required')
        self.owner_argv=owner_argv;self.cancelled=cancelled;self.clock=clock;self.previous=None
        self.check,self.sleep=check,sleep;self.failed=False;self.pins={};self.identity=None
        self.view=object.__new__(ReceiptPair)
        self.view.directory=self.directory;self.view.failed=False;self.view.checkpoint=self._check
    def _check(self):
        try:
            if self.failed:raise ValueError('barrier failure latched')
            self.check()
            if self.identity is not None:
                now=self.clock()
                if type(now) not in (int,float) or not math.isfinite(now) or now<self.request['started'] or (self.previous is not None and now<self.previous) or now>=self.request['work_deadline']:
                    self.failed=True
                    raise TimeoutError('original POST permit deadline/clock')
                self.previous=now
            if self.cancelled() is not False:
                self.failed=True
                raise ValueError('cross-process cancellation')
        except BaseException:
            self.failed=True;raise
    def _read(self,name,cap):
        self._check()
        raw,seal=self.view._read(self.directory/name,cap)
        if name in self.pins and self.pins[name]!=(seal,raw):raise ValueError('retained receipt changed')
        self.pins[name]=(seal,raw)
        return decode(raw)
    def _wait(self,name,cap):
        while True:
            self._check()
            if self.failed:raise ValueError('barrier failure latched')
            try:return self._read(name,cap)
            except FileNotFoundError:
                if name in self.pins:raise ValueError('retained receipt removed')
                self.sleep(.05)
    def _identity(self,value):
        expected=self.identity
        if expected is None:
            request_sha=hashlib.sha256(self.pins['reader-command/request.json'][1]).hexdigest()
            deadline=self.request.get('work_deadline')
            if type(deadline) not in (int,float) or not math.isfinite(deadline) or type(self.request.get('started')) not in (int,float) or not math.isfinite(self.request['started']) or not 0<=self.request['started']<deadline:raise ValueError('original reader deadline required')
            owner=hashlib.sha256(json.dumps(dict(run=self.run,source=self.source,request_sha256=request_sha,argv=self.owner_argv,deadline=deadline),sort_keys=True,separators=(',',':')).encode()).hexdigest()
            expected=dict(run=self.run,source=self.source,owner=owner,request_sha256=request_sha)
            ReceiptPair._sha(expected['owner']);ReceiptPair._sha(expected['request_sha256'])
        if any(value.get(k)!=v for k,v in expected.items()):raise ValueError('receipt identity mismatch')
        if value.get('schema')!='nbsr-reader-lifecycle-receipt-v2' or value.get('campaign_valid') is not False:raise ValueError('receipt schema/validity')
        return expected
    def wait_closed(self):
        try:
            if self.identity is not None:raise ValueError('one closure barrier')
            self.request=self._wait('reader-command/request.json',8192)
            v=self._wait('reader-closed-v2.json',2048)
            self.identity=self._identity(v)
            if v.get('state')!='CLOSED_UNSETTLED':raise ValueError('closure state')
            ReceiptPair._sha(v.get('capture_sha256'))
            permit=dict(schema='nbsr-reader-lifecycle-v1',run=self.run,source=self.source,owner=self.identity['owner'],operation='clock-probes-only',anchor=self.request.get('started'),deadline=self.request.get('work_deadline'),capture_sha256=v['capture_sha256'])
            if v.get('post_permit')!=permit:raise ValueError('POST permit binding')
            self.post_binding=dict(closed_receipt_sha256=hashlib.sha256(self.pins['reader-closed-v2.json'][1]).hexdigest(),request_sha256=self.identity['request_sha256'],post_permit=permit)
            self._read('reader-command/request.json',8192)
            if hashlib.sha256(self.pins['reader-command/request.json'][1]).hexdigest()!=self.identity['request_sha256']:raise ValueError('request binding')
            return v
        except BaseException:self.failed=True;raise
    def verify(self):
        try:
            if self.failed or self.identity is None:raise ValueError('closed barrier required')
            for name in tuple(self.pins):self._read(name,8192 if name in ('acquisition-result.json','reader-command/request.json','reader-command/supervision.json') else 2048)
        except BaseException:self.failed=True;raise
    def post_window(self,window):
        self.verify()
        return _PostWindow(self,window)

    def wait_complete(self):
        try:
            self.verify()
            v=self._wait('reader-settled-v2.json',2048);self._identity(v)
            if v.get('state')!='SETTLED_REQUIRES_OTHER_GATES' or v.get('closed_receipt_sha256')!=hashlib.sha256(self.pins['reader-closed-v2.json'][1]).hexdigest():raise ValueError('settlement binding')
            ReceiptPair._sha(v.get('settlement_sha256'))
            result=self._wait('acquisition-result.json',8192)
            if result.get('identity')!=self.identity or result.get('status')!='LOCAL_READER_JOINED' or result.get('joined') is not True or result.get('errors')!=[]:raise ValueError('acquisition failed/mismatched')
            owner=result.get('reader_value',{})
            if not (owner.get('status')=='LOCAL_WORKER_COMPLETED' and type(owner.get('exit_code')) is int and owner.get('exit_code')==0 and owner.get('leader_reaped') is True and owner.get('group_exit_observed') is True and owner.get('owned_handles') is False and owner.get('drain_failure') is None and owner.get('errors')==[]):raise ValueError('ownership incomplete')
            retained_owner=self._read('reader-command/supervision.json',8192)
            if retained_owner!=owner:raise ValueError('retained supervision contradicts acquisition')
            if hashlib.sha256(self.pins['reader-command/supervision.json'][1]).hexdigest()!=v['settlement_sha256']:raise ValueError('settlement receipt changed')
            self.verify();return result
        except BaseException:self.failed=True;raise

class _PostWindow:
    def __init__(self,barrier,original):
        self.barrier,self.original=barrier,original
        self.phase_end=min(original.phase_end,barrier.request['work_deadline'])
        self.end=min(original.end,barrier.request['work_deadline'])
    def check_work(self):
        try:
            self.barrier._check();self.original.check_work()
        except BaseException:
            self.barrier.failed=True;raise
    def post_budget(self):
        try:
            self.check_work()
            remaining=min(self.original.post_budget(),self.end-self.barrier.clock())
            if remaining<=0:raise TimeoutError('original POST permit expired')
            return remaining
        except BaseException:
            self.barrier.failed=True;raise
