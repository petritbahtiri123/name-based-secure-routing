"""Bounded passive prefix consumer. No SSH, polling, workload or lifecycle control.

The owner supplies authenticated, complete prefixes of one immutable-identity
source file. Source progress/final does NOT qualify the overall campaign.
"""
from .capture import CaptureSession
from .feed import export
from .adapters import MAX_BYTES

class PrefixBridge:
    def __init__(self, directory, inbox, source_identity, experiment, *, capture_budget=1024*1024, origin_profile="nbsr"):
        self.capture = CaptureSession(directory, source_identity, origin_record=True, origin_profile=origin_profile, max_session_bytes=capture_budget)
        self.identity = source_identity
        self.inbox = inbox
        self.experiment = experiment
        self._prefix = b''
        self._published = None
        self._unavailable = False

    def accept(self, prefix):
        if self._unavailable:
            raise ValueError('Bridge unavailable after failure or closure')
        try:
            if not isinstance(prefix, bytes) or len(prefix) > MAX_BYTES:
                raise ValueError('Source prefix must be bounded bytes')
            if not prefix.startswith(self._prefix):
                raise ValueError('Source truncated or rewritten')
            if prefix == self._prefix:
                return None
            self.capture.append(prefix[len(self._prefix):], offset=len(self._prefix), source_identity=self.identity)
            self._prefix = prefix
            path = self.capture.snapshot_path()
            if path is not None and path != self._published:
                packet = export(path, self.inbox, self.experiment)
                self._published = path
                return packet
            return None
        except Exception:
            self._unavailable = True
            raise

    def finish(self):
        if self._unavailable:
            raise ValueError('Bridge unavailable after failure or closure')
        self._unavailable = True
        return self.capture.finish()

class FramedBridge:
    """Bind separately owned acquisition frames to the planned run and file."""
    def __init__(self, directory, inbox, run, source, *, origin_profile="nbsr"):
        self.bridge = PrefixBridge(directory, inbox, run, run, origin_profile=origin_profile)
        self.run, self.source = run, source
        self.sequence = 0
        self.file_identity = None
        self.failed = False
        self.ended = False
        self.started = False

    def accept_frame(self, raw):
        import base64
        import json
        if self.failed or self.ended:
            raise ValueError('Frame consumer closed')
        try:
            if not isinstance(raw, bytes) or len(raw) > 6*1024*1024:
                raise ValueError('Frame limit')
            def unique(pairs):
                value = {}
                for key, item in pairs:
                    if key in value: raise ValueError('Duplicate frame key')
                    value[key] = item
                return value
            row = json.loads(raw, object_pairs_hook=unique)
            if row.get('run') != self.run:
                raise ValueError('Wrong run')
            if row.get('schema') == 'nbsr-lab-reader-start-v1':
                if self.started or set(row) != {'schema','run','source','state','cadence_seconds','lifetime_seconds','wire_budget'} or row['source'] != self.source or row['state'] != 'waiting-for-source' or type(row['cadence_seconds']) is not int or row['cadence_seconds'] != 5 or type(row['lifetime_seconds']) is not int or not 1 <= row['lifetime_seconds'] <= 90 or type(row['wire_budget']) is not int or not 1 <= row['wire_budget'] <= 4*1024*1024:
                    raise ValueError('Invalid reader START')
                self.started = True
                return None
            if not self.started:
                raise ValueError('Reader START missing')
            if row.get('schema') == 'nbsr-lab-reader-ended-v1':
                if set(row) != {'schema','run','reason','observations'} or row['reason'] not in ('bounded-lifetime-expired', 'source-final-observed') or type(row['observations']) is not int or row['observations'] != self.sequence:
                    raise ValueError('Bad reader closure')
                self.ended = True
                return None
            if set(row) != {'schema','run','source','sequence','file_identity','prefix'} or row['schema'] != 'nbsr-lab-prefix-v1' or row['source'] != self.source:
                raise ValueError('Unexpected frame identity or fields')
            if type(row['sequence']) is not int or row['sequence'] != self.sequence+1:
                raise ValueError('Frame sequence gap')
            identity = row['file_identity']
            if not isinstance(identity,list) or len(identity)!=2 or any(type(v) is not int or v<0 for v in identity):
                raise ValueError('Invalid file identity')
            if self.file_identity is not None and identity != self.file_identity:
                raise ValueError('Source replaced')
            prefix = base64.b64decode(row['prefix'], validate=True)
            result = self.bridge.accept(prefix)
            self.file_identity = identity
            self.sequence = row['sequence']
            return result
        except Exception:
            self.failed = True
            raise

class FrameLogPump:
    """Caller schedules polls of the separately owned SSH stdout log."""
    def __init__(self, consumer, wire_budget):
        if not 1 <= wire_budget <= 4*1024*1024: raise ValueError('Wire budget')
        self.consumer, self.budget = consumer, wire_budget
        self.state = {}
        self.offset = 0
        self.failed = False

    def poll(self, path):
        from .remote_reader import read_prefix
        if self.failed: raise ValueError('Log pump failed')
        try:
            raw = read_prefix(path, self.state, self.budget)
            end = raw.rfind(b'\n')+1
            for line in raw[self.offset:end].splitlines():
                self.consumer.accept_frame(line)
            self.offset = end
        except Exception:
            self.failed = True
            raise
