"""Bounded local byte extraction only: no files, network, timers or workload control."""
import hashlib

from .adapters import MAX_BYTES, decode
from .grouped import PROGRESS_SCHEMA, FINAL_SCHEMA, normalize_grouped, validate_shape

MAX_LINE_BYTES = 65536
MAX_SOURCE_RECORDS = 4096
DIAGNOSTIC_SCHEMA = 'nbsr-rust-ownership-v1'


class StdoutExtractor:
    """One declared append-only source; any error permanently stops publication.

    The future transport must independently verify the source/file identity.
    Offsets and identities supplied here are checks on that caller's contract,
    not authentication or proof that a remote file has not been replaced.
    """

    def __init__(self, source_identity, *, origin_record=False, origin_profile="nbsr"):
        if type(source_identity) is not str or not 1 <= len(source_identity) <= 128:
            raise ValueError('Source identity must be 1-128 characters')
        if type(origin_record) is not bool:
            raise ValueError('origin_record must be boolean')
        if type(origin_profile) is not str or origin_profile not in ("nbsr", "direct"):
            raise ValueError("Unknown declared origin profile")
        if origin_profile == "direct" and not origin_record:
            raise ValueError("Direct origin profile requires origin_record")
        self._origin_profile = origin_profile
        self._expect_origin = origin_record
        self._origin_seen = False
        self._identity = source_identity
        self._raw = bytearray()
        self._pending = b''
        self._artifact = bytearray()
        self._grouped = []
        self._ledger = []
        self._final = False
        self._closed = False
        self._failed = False
        self._validity = 'unavailable'

    @property
    def retained_raw(self):
        """Captured bytes remain accessible after failure, for private evidence.

        A chunk exceeding the total source-byte limit or conflicting with the
        identity/offset is not incorporated; the caller retains it separately.
        Line/record-limit failures within that total cap retain captured bytes.
        """
        return bytes(self._raw)

    def _available(self):
        if self._failed:
            raise ValueError('Extraction unavailable after a prior failure')

    def append(self, chunk, *, offset, source_identity):
        self._available()
        try:
            if type(offset) is not int or offset != len(self._raw):
                raise ValueError('Source offset must continue the exact captured prefix')
            if source_identity != self._identity:
                raise ValueError('Source identity changed')
            if type(chunk) is not bytes:
                raise ValueError('Source chunks must be bytes')
            if len(self._raw) + len(chunk) > MAX_BYTES:
                raise ValueError('Captured source exceeds 4 MiB limit')

            start = len(self._raw) - len(self._pending)
            self._raw.extend(chunk)
            # Retain admitted failure bytes independently of transport chunking.
            if self._closed:
                raise ValueError('Extraction is already closed')
            if self._final and chunk:
                raise ValueError('Source bytes after final marker')
            combined = self._pending + chunk
            position = 0
            while True:
                end = combined.find(b'\n', position)
                if end < 0:
                    break
                wire = combined[position:end + 1]
                position = end + 1
                if self._final:
                    raise ValueError('Source record after final marker')
                if len(wire) > MAX_LINE_BYTES:
                    raise ValueError('Source line exceeds 64 KiB limit')
                if len(self._ledger) >= MAX_SOURCE_RECORDS:
                    raise ValueError('Source exceeds 4096 records')
                body = wire[:-2] if wire.endswith(b'\r\n') else wire[:-1]
                if b'\r' in body:
                    raise ValueError('Bare carriage return inside source record')
                # JSON's bytes decoder also supports UTF-16; this contract does not.
                try:
                    text = wire.decode('utf-8')
                except UnicodeError as error:
                    raise ValueError('Source is not UTF-8') from error
                row = decode(text)
                schema = row.get('schema')
                if schema in (PROGRESS_SCHEMA, FINAL_SCHEMA):
                    if self._expect_origin and not self._origin_seen:
                        raise ValueError('Expected origin record before grouped data')
                    validate_shape(row)
                    self._artifact.extend(wire)
                    self._grouped.append(row)
                    self._final = schema == FINAL_SCHEMA
                    kind = 'grouped'
                elif schema == 'nbsr-origin-monotonic-v1' and self._expect_origin:
                    keys = {'origin_lo_ns', 'origin_hi_ns', 'sample_before_ns',
                            'sample_after_ns'}
                    if self._origin_profile == 'nbsr':
                        keys |= {'client_origin_ns', 'client_sample_ns'}
                    if self._origin_seen or self._grouped or set(row) != keys | {'schema'}:
                        raise ValueError('Unexpected origin record shape or position')
                    if any(type(row[k]) is not int or not 0 <= row[k] < 2**64 for k in keys):
                        raise ValueError('Invalid origin integer')
                    lo, hi, a, b = (row[k] for k in ('origin_lo_ns', 'origin_hi_ns', 'sample_before_ns', 'sample_after_ns'))
                    if not (0 <= lo <= hi <= b and a <= b and hi-lo == b-a and b-a <= 1_000_000):
                        raise ValueError('Invalid origin bounds')
                    self._origin_seen = True
                    kind = 'origin'
                elif schema == DIAGNOSTIC_SCHEMA and row.get('event') == 'diagnostic':
                    kind = 'diagnostic'
                else:
                    raise ValueError('Unreviewed source record')
                self._ledger.append(dict(start=start, end=start + len(wire), kind=kind,
                                         sha256=hashlib.sha256(wire).hexdigest()))
                start += len(wire)

            remaining = combined[position:]
            if self._final and remaining:
                raise ValueError('Source bytes after final marker')
            if len(remaining) > MAX_LINE_BYTES:
                raise ValueError('Pending source line exceeds 64 KiB limit')
            self._pending = remaining
            if self._grouped:
                # Preserve failed measurements as invalid evidence, not clean charts.
                normalized = normalize_grouped(self._grouped)[0]
                self._validity = normalized['stream']['validity']
            return self.snapshot()
        except Exception as error:
            self._failed = True
            if isinstance(error, ValueError):
                raise
            # Adapter arithmetic/type failures must not expose a stale valid prefix.
            raise ValueError('Source extraction failed; publication unavailable') from error

    def snapshot(self):
        self._available()
        raw = bytes(self._raw)
        artifact = bytes(self._artifact) if self._grouped else None
        return dict(raw=raw, artifact=artifact, ledger=dict(
            schema='nbsr-lab-local-extraction-v2' if self._expect_origin else 'nbsr-lab-local-extraction-v1',
            source_bytes=len(raw), source_sha256=hashlib.sha256(raw).hexdigest(),
            consumed_bytes=len(raw) - len(self._pending), pending_bytes=len(self._pending),
            artifact_sha256=hashlib.sha256(artifact).hexdigest() if artifact else None,
            state='final' if self._final else 'partial',
            measurement_validity=self._validity,
            records=[dict(record) for record in self._ledger]))

    def finish(self):
        """Explicit owner closure, never inferred from silence or a disconnect."""
        self._available()
        if self._pending or not self._final:
            self._failed = True
            raise ValueError('Source closed without a complete newline-framed final marker')
        self._closed = True
        return self.snapshot()
