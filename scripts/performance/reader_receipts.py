"""Versioned bounded local receipts; closure is explicitly not campaign validity."""
import hashlib,json,os,pathlib,stat
from scripts.performance import reader_output_limits as limits


def decode(raw):
    def pairs(rows):
        result={}
        for key,value in rows:
            if key in result:raise ValueError('duplicate JSON key')
            result[key]=value
        return result
    def invalid(value):raise ValueError('nonfinite JSON constant')
    return json.loads(raw,object_pairs_hook=pairs,parse_constant=invalid)

class ReceiptPair:
    NAMES={'closed':'reader-closed-v2.json','settled':'reader-settled-v2.json'}
    def __init__(self,directory,claim,identity,*,checkpoint):
        if claim.purpose!='live/completion':raise ValueError('existing completion allocation required')
        if type(identity) is not dict or set(identity)!={'run','source','owner','request_sha256'}:raise ValueError('exact receipt identity')
        if any(type(v) is not str or not v for v in identity.values()):raise ValueError('nonempty receipt identity')
        self.directory=pathlib.Path(directory);self.claim=claim;self.identity=dict(identity);self.checkpoint=checkpoint
        self.pins={};self.failed=False;self.result_written=False;self.result_pin=None
        self._safe_directory()
    def _safe_directory(self):
        for p in (self.directory,*self.directory.parents):
            st=p.lstat()
            if not stat.S_ISDIR(st.st_mode) or getattr(st,'st_file_attributes',0)&1024:raise ValueError('unsafe receipt directory')
    def _check(self):
        if self.failed:raise ValueError('receipt failure latched')
        self.checkpoint();self._safe_directory()
    @staticmethod
    def _sha(value):
        if type(value) is not str or len(value)!=64 or any(c not in '0123456789abcdef' for c in value):raise ValueError('exact receipt SHA256')
        return value
    def _read(self,path,cap=2048):
        self._check()
        for parent in (path.parent,*path.parent.parents):
            info=parent.lstat()
            if not stat.S_ISDIR(info.st_mode) or getattr(info,'st_file_attributes',0)&1024:raise ValueError('unsafe receipt parent')
        def identity(st):
            if not stat.S_ISREG(st.st_mode) or st.st_nlink!=1 or st.st_size>cap or getattr(st,'st_file_attributes',0)&1024:raise ValueError('receipt type/size/alias')
            return st.st_dev,st.st_ino,st.st_size,st.st_mtime_ns,st.st_ctime_ns
        before=identity(path.lstat())
        with path.open('rb') as f:
            opened=identity(os.fstat(f.fileno()))
            if opened[:4]!=before[:4]:raise ValueError('receipt replaced at open')
            raw=f.read(cap+1)
            if len(raw)>cap or identity(os.fstat(f.fileno()))!=opened:raise ValueError('receipt changed during read')
        if identity(path.lstat())!=before:raise ValueError('receipt replaced')
        self._check()
        return raw,(before,hashlib.sha256(raw).hexdigest())
    @staticmethod
    def _encode(value,cap):
        raw=bytearray()
        for part in json.JSONEncoder(sort_keys=True,separators=(',',':'),allow_nan=False).iterencode(value):
            if len(part)>cap-len(raw):raise ValueError('receipt cap exceeded')
            chunk=part.encode()
            if len(chunk)>cap-len(raw):raise ValueError('receipt cap exceeded')
            raw.extend(chunk)
        return bytes(raw)

    def publish_result(self,value):
        try:
            self._check()
            if self.result_written:raise ValueError('one acquisition result only')
            if type(value) is not dict or value.get('status')!='LOCAL_READER_JOINED':raise ValueError('successful joined result required')
            if value.get('joined') is not True or type(value.get('errors')) is not list or value['errors'] or value.get('identity')!=self.identity:raise ValueError('contradictory acquisition success or identity')
            self.verify_pair()
            self.result_written=True
            try:raw=self._encode(value,8192)
            except ValueError as error:raise ValueError('acquisition result exceeds8KiB partition') from error
            with (self.directory/'acquisition-result.json').open('xb') as stream:
                writer=limits.BoundedWriter(self.claim,stream);writer.write(raw);writer.finish();os.fsync(stream.fileno())
            observed,seal=self._read(self.directory/'acquisition-result.json',8192)
            if observed!=raw:raise ValueError('acquisition result publication mismatch')
            self.result_pin=(seal,raw)
            self.verify_complete()
        except BaseException:
            self.failed=True;limits.mark_unknown(self.claim,'acquisition_result');raise

    def _publish(self,kind,value):
        self._check()
        if kind in self.pins:raise ValueError('one immutable receipt only')
        raw=self._encode(value,2048)
        path=self.directory/self.NAMES[kind];pending=path.with_suffix('.json.pending')
        # Reserve both names before I/O, never refund even after publication.
        limits.charge_alias(self.claim,len(raw))
        with pending.open('xb') as f:
            writer=limits.BoundedWriter(self.claim,f);writer.write(raw);writer.finish();os.fsync(f.fileno())
        self._check()
        os.link(pending,path)  # exclusive destination, no overwrite on either OS
        pending.unlink()  # only this operation's completed temporary alias
        observed,seal=self._read(path)
        if observed!=raw:raise ValueError('published receipt mismatch')
        self.pins[kind]=(seal,raw)
        return value
    def _verify(self,kind):
        if kind not in self.pins:raise ValueError('required receipt missing')
        raw,seal=self._read(self.directory/self.NAMES[kind]);expected,encoded=self.pins[kind]
        if seal!=expected or raw!=encoded:raise ValueError('immutable receipt changed')
        return decode(raw)
    def publish_closed(self,capture_sha256,*,post_permit=None):
        try:
            self._check()
            return self._publish('closed',dict(schema='nbsr-reader-lifecycle-receipt-v2',state='CLOSED_UNSETTLED',
                **self.identity,capture_sha256=self._sha(capture_sha256),campaign_valid=False,
                **({"post_permit":post_permit} if post_permit is not None else {})))
        except BaseException:
            self.failed=True;limits.mark_unknown(self.claim,'closed_receipt');raise
    def publish_settled(self,*,valid,settlement_sha256):
        try:
            self._check();self._verify('closed')
            if valid is not True:raise ValueError('settlement failure')
            return self._publish('settled',dict(schema='nbsr-reader-lifecycle-receipt-v2',state='SETTLED_REQUIRES_OTHER_GATES',
                **self.identity,closed_receipt_sha256=self.pins['closed'][0][1],settlement_sha256=self._sha(settlement_sha256),campaign_valid=False))
        except BaseException:
            self.failed=True;limits.mark_unknown(self.claim,'settled_receipt');raise
    def verify_pair(self):
        try:
            self._check();self._verify('closed');settled=self._verify('settled')
            if self.result_written:
                if self.result_pin is None:raise ValueError('acquisition result incomplete')
                raw,seal=self._read(self.directory/'acquisition-result.json',8192)
                if (seal,raw)!=self.result_pin:raise ValueError('immutable acquisition result changed')
            return settled
        except BaseException:
            self.failed=True;limits.mark_unknown(self.claim,'receipt_verification');raise

    def verify_complete(self):
        try:
            self.verify_pair()
            if not self.result_written or self.result_pin is None:raise ValueError('acquisition result required')
            return decode(self.result_pin[1])
        except BaseException:
            self.failed=True;limits.mark_unknown(self.claim,'acquisition_verification');raise
