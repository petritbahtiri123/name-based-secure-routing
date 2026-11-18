"""Offline launcher binding: exact bounded.run request, capture and shared receipts."""
import hashlib
import math
import json
import time
import os
from scripts.performance.reader_handoff import ReaderHandoff
from scripts.performance.reader_receipts import ReceiptPair,decode

class ReaderLauncher:
    def __init__(self, *, run, source, directory, claim, capture, clock, budget_check=lambda:None):
        self.run,self.source,self.directory,self.claim=run,source,directory,claim
        self.capture,self.clock=capture,clock
        self.budget_check=budget_check
        self.handoff=self.receipts=None
        self.failed=False
        self.prepared=False
        self.cancel_signal_attempted=False;self.cancel_signal_error=None

    @property
    def lifecycle(self):
        return self.handoff.lifecycle if self.handoff is not None else None

    def invalidate(self):
        self.failed=True
        if self.handoff is not None:self.handoff.invalidate()
        if self.receipts is not None:self.receipts.failed=True
        if not self.cancel_signal_attempted:
            self.cancel_signal_attempted=True
            try:
                view=object.__new__(ReceiptPair);view.directory=self.directory/'reader-command';view._safe_directory()
                try:
                    with (view.directory/'cancel').open('xb') as stream:
                        stream.flush();os.fsync(stream.fileno())
                except FileExistsError:pass  # Existing marker already means cancellation, never reset.
            except BaseException as error:self.cancel_signal_error=type(error).__name__

    def _check(self):
        if self.failed:raise ValueError('launcher failure latched')
        try:self.budget_check()
        except BaseException:self.invalidate();raise
        if self.handoff is None:raise ValueError('request binding required')
        if self.lifecycle is not None:
            self.lifecycle._check()
            if self.lifecycle.state=='CLOSED_UNSETTLED':self.capture.verify()

    def prepare(self,native,request,anchor,deadline):
        try:
            if self.failed or self.prepared:raise ValueError('one request binding only')
            self.prepared=True
            if request.parent!=self.directory/'reader-command' or request.name!='request.json':raise ValueError('fixed reader request path')
            # Reuse bounded, single-link, identity checked read; no receipt allocation/writes.
            view=object.__new__(ReceiptPair)
            view.directory=self.directory;view.failed=False;view.checkpoint=lambda:None
            raw,seal=view._read(request,8192)
            value=decode(raw)
            if any(type(x) not in (int,float) or not math.isfinite(x) for x in (value.get('started'),value.get('work_deadline'),anchor,deadline)):raise ValueError('finite original request interval')
            if value.get('started')!=anchor or value.get('work_deadline')!=deadline or value.get('output')!=str(request.parent):raise ValueError('reader request deadline/path mismatch')
            self.handoff=ReaderHandoff(run=self.run,source=self.source,request_sha256=hashlib.sha256(raw).hexdigest(),
                argv=tuple(native.argv),anchor=anchor,deadline=deadline,
                caps={'capture':262144,'receipts':16384},clock=self.clock,capture=self.capture)
            self.request=request;self.request_pin=(seal,raw);self.request_view=view
        except BaseException:
            self.invalidate();raise

    def _verify_request(self):
        raw,seal=self.request_view._read(self.request,8192)
        if (seal,raw)!=self.request_pin:raise ValueError('reader request changed')

    def checkpoint(self,native):
        try:
            self._check();self._verify_request();self.handoff.checkpoint(native)
            if self.lifecycle is not None and self.lifecycle.state=='CLOSED_UNSETTLED':
                self.capture.verify()
                if self.receipts is None:
                    identity=dict(self.lifecycle.identity,request_sha256=self.handoff.request_sha256)
                    self.receipts=ReceiptPair(self.directory,self.claim,identity,checkpoint=self._check)
                    self.post_permit=self.lifecycle.begin_post()
                    self.receipts.publish_closed(self.lifecycle._capture_sha,post_permit=self.post_permit)
        except BaseException:
            self.invalidate();raise

    def consume(self,native):
        try:
            self._check();self._verify_request();return self.handoff.consume(native)
        except BaseException:
            self.invalidate();raise

    def settle(self,settlement_sha256):
        try:
            self._check();self._verify_request()
            if self.receipts is None or not self.handoff.consumed:raise ValueError('closure receipt required')
            self.receipts.publish_settled(valid=True,settlement_sha256=settlement_sha256)
            self.lifecycle.finish_settlement(valid=True,receipt_sha256=settlement_sha256)
        except BaseException:
            self.invalidate();raise

    def finish(self,result):
        try:
            self._check();self._verify_request()
            if self.receipts is None:raise ValueError('settlement missing')
            value=dict(result,identity=dict(self.receipts.identity))
            self.receipts.publish_result(value)
            self.receipts.verify_complete()
            return value
        except BaseException:
            self.invalidate();raise

    def wait_post(self,path,*,sleep=time.sleep):
        """Consume the existing bounded CALIBRATION receipt; never creates a writer."""
        try:
            self._check();self.receipts.verify_complete()
            if path!=self.directory.parent/'cells/baseline8/CALIBRATION.json':raise ValueError('fixed POST outcome path')
            if hasattr(self,'post_pin'):raise ValueError('one POST outcome only')
            while True:
                self._check()
                try:raw,seal=self.request_view._read(path,8192);break
                except FileNotFoundError:sleep(.05)
            value=decode(raw)
            expected=dict(closed_receipt_sha256=self.receipts.pins['closed'][0][1],
                          request_sha256=self.handoff.request_sha256,post_permit=self.post_permit)
            if value.get('reader_lifecycle')!=expected or value.get('all_samples_retained') is not True:
                raise ValueError('POST outcome binding/validation')
            self.lifecycle.finish_post(self.post_permit,span_ns=value.get('span_ns'),probes_valid=True)
            self.post_pin=(path,seal,raw)
            self.verify_post()
        except BaseException:self.invalidate();raise

    def verify_post(self):
        try:
            self._check()
            if not hasattr(self,'post_pin'):raise ValueError('POST outcome missing')
            path,expected,encoded=self.post_pin
            raw,seal=self.request_view._read(path,8192)
            if (seal,raw)!=(expected,encoded):raise ValueError('POST outcome changed')
            self.receipts.verify_complete()
        except BaseException:self.invalidate();raise
