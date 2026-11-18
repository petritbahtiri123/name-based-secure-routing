"""Offline successor handoff. No launcher; capture callback is a trusted adapter seam."""
from scripts.performance.reader_settlement import BoundReaderOwner, Lifecycle

class ReaderHandoff:
    def __init__(self, *, run, source, request_sha256, argv, anchor, deadline, caps, clock, capture):
        self.run,self.source,self.request_sha256,self.argv=run,source,request_sha256,argv
        self.anchor,self.deadline,self.caps,self.clock=anchor,deadline,caps,clock
        self.capture=capture
        self.bound=self.lifecycle=None
        self.failed=self.consumed=False

    def invalidate(self):
        """Campaign failure is irreversible even if its local cause is restored."""
        self._fail()

    def _fail(self):
        self.failed=True
        if self.lifecycle is not None:self.lifecycle.state='INVALID'

    def _verify(self, native):
        if self.failed:raise ValueError('handoff failure latched')
        if self.bound is not None and self.bound.native is not native:raise ValueError('different native owner')

    def checkpoint(self, native):
        try:
            self._verify(native)
            if self.bound is None:
                if not native.owned:return  # initial scan before owner.start
                self.bound=BoundReaderOwner(native,run=self.run,source=self.source,request_sha256=self.request_sha256,
                                            argv=self.argv,deadline=self.deadline)
                self.lifecycle=Lifecycle(run=self.run,source=self.source,owner=self.bound.identity,anchor=self.anchor,
                                         deadline=self.deadline,caps=self.caps,clock=self.clock)
            self.lifecycle.checkpoint(self.bound,lambda:self.capture(dict(self.lifecycle.identity)))
        except BaseException:
            self._fail();raise

    def consume(self,native):
        try:
            self._verify(native)
            if self.bound is None:return False
            self.lifecycle._check()
            if self.lifecycle.state=='OPEN':return False
            if self.lifecycle.state!='CLOSED_UNSETTLED' or self.consumed or self.bound.owned:
                raise ValueError('one exact closed-unsettled handoff required')
            self.consumed=True
            return True
        except BaseException:
            self._fail();raise
