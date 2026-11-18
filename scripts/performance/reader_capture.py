"""Offline capture adapter using the real frame consumer and extractor, no transport."""
import hashlib
import json
import os
import pathlib
import stat
from lab.extractor import StdoutExtractor

class FinalCapture:
    def __init__(self, acquisition, consumer, pump, *, run, source, wire_cap, log_path, origin_profile='nbsr'):
        if type(wire_cap) is not int or not 1<=wire_cap<=131072:raise ValueError('fixed wire cap')
        self.acquisition,self.consumer,self.pump=acquisition,consumer,pump
        self.run,self.source,self.wire_cap,self.origin_profile=run,source,wire_cap,origin_profile
        self.used=self.failed=False
        self.raw=self.wire=None
        self.log_path=pathlib.Path(log_path)
        self.seals={}

    @staticmethod
    def _read(path,cap):
        for parent in (path,*path.parents):
            info=parent.lstat()
            if stat.S_ISLNK(info.st_mode) or getattr(info,'st_file_attributes',0)&1024:
                raise ValueError('redirected persisted capture path')
        def identity(info):
            if not stat.S_ISREG(info.st_mode) or info.st_nlink!=1 or info.st_size>cap:
                raise ValueError('persisted capture type/alias/bound')
            return info.st_dev,info.st_ino,info.st_size,info.st_mtime_ns,info.st_ctime_ns
        before=identity(path.lstat())
        with path.open('rb') as stream:
            opened=identity(os.fstat(stream.fileno()))
            # Windows path-stat and handle-stat expose ctime with different semantics.
            # Compare stable identity/size/mtime across them; ctime within each view.
            if opened[:4]!=before[:4]:raise ValueError('capture replaced at open')
            raw=stream.read(cap+1)
            if len(raw)>cap or identity(os.fstat(stream.fileno()))!=opened:raise ValueError('capture changed during read')
        if identity(path.lstat())!=before:raise ValueError('capture replaced after read')
        return raw,(before,hashlib.sha256(raw).hexdigest())

    def _seal(self,path,expected):
        raw,seal=self._read(path,self.wire_cap)
        if raw!=expected:raise ValueError('persisted bytes differ from validated capture')
        self.seals[path]=seal

    def _quiescent(self):
        a,c,p=self.acquisition,self.consumer,self.pump
        if a.errors or a.pump_thread is None or a.pump_thread.is_alive() or not a.transport_closed.is_set():
            raise ValueError('capture writer not quiescent')
        if c.run!=self.run or c.source!=self.source or p.consumer is not c:
            raise ValueError('capture source binding')
        if not c.started or not c.ended or c.failed or p.failed:
            raise ValueError('incomplete framed reader')
        wire=p.state.get('prefix')
        if type(wire) is not bytes or len(wire)>self.wire_cap or p.offset!=len(wire):
            raise ValueError('incomplete or unbounded frame bytes')
        if not c.bridge.capture._closed or c.bridge.capture._failed:
            raise ValueError('capture persistence not finalized')
        return c.bridge._prefix,wire

    def __call__(self, identity):
        try:
            if self.used or self.failed:raise ValueError('one final capture only')
            self.used=True
            if type(identity) is not dict or set(identity)!={'run','source','owner'} or identity['run']!=self.run or identity['source']!=self.source:
                raise ValueError('closure identity')
            self.acquisition.close_capture()
            raw,wire=self._quiescent()
            if type(raw) is not bytes or len(raw)>self.wire_cap:raise ValueError('bounded source bytes')
            parser=StdoutExtractor(self.run,origin_record=True,origin_profile=self.origin_profile)
            parser.append(raw,offset=0,source_identity=self.run)
            result=parser.finish();ledger=result['ledger']
            digest=hashlib.sha256(raw).hexdigest()
            if (ledger['state']!='final' or ledger['measurement_validity']!='valid' or ledger['pending_bytes']!=0
                    or ledger['consumed_bytes']!=len(raw) or ledger['source_sha256']!=digest):
                raise ValueError('independent final source validation')
            directory=self.consumer.bridge.capture._directory/f'snapshot-{self.consumer.bridge.capture._sequence:04d}'
            self._seal(self.log_path,wire)
            if self.seals[self.log_path][0][:2]!=self.pump.state.get('identity'):
                raise ValueError('framing log identity changed since pump')
            self._seal(directory/'raw.bin',raw)
            self._seal(directory/'grouped.ndjson',result['artifact'])
            manifest=dict(schema='nbsr-lab-local-capture-v1',declared_source_identity=self.run,
                          source_identity_verified=False,owner_closed=True,ledger=ledger)
            self._seal(directory/'manifest.json',json.dumps(manifest,sort_keys=True,allow_nan=False).encode())
            self.raw,self.wire=raw,wire
            return dict(identity,quiescent=True,final_valid=True,sha256=digest)
        except BaseException:
            self.failed=True
            raise

    def verify(self):
        try:
            if self.failed or self.raw is None:raise ValueError('final capture unavailable')
            if self._quiescent()!=(self.raw,self.wire):raise ValueError('sealed capture changed')
            if len(self.seals)!=4:raise ValueError('persisted seals missing')
            for path,seal in self.seals.items():
                if self._read(path,self.wire_cap)[1]!=seal:raise ValueError('persisted sealed capture changed')
        except BaseException:
            self.failed=True
            raise
