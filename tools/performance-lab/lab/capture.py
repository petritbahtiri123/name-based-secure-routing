"""Opt-in local evidence persistence. No network, watcher, feed or workload control."""
import json
import os
from pathlib import Path
from .extractor import StdoutExtractor

MAX_SESSION_BYTES = 64 * 1024 * 1024
MAX_SNAPSHOTS = 4096


class CaptureSession:
    """Single owner, new private directory only; no recovery/resume contract.

    Caller authenticates the source independently. Returned immutable snapshot
    paths are eligible for the existing exporter only after this method returns.
    Do not independently watch the directory or reuse old paths after a failure.
    """
    def __init__(self, directory, source_identity, *, origin_record=False, max_session_bytes=None):
        if max_session_bytes is not None and (type(max_session_bytes) is not int or not 1 <= max_session_bytes <= MAX_SESSION_BYTES):
            raise ValueError('Invalid capture budget')
        self._max_session_bytes = max_session_bytes
        self._parser = StdoutExtractor(source_identity, origin_record=origin_record)
        self._directory = Path(directory)
        # Fail rather than reuse another session or follow an existing link.
        self._directory.mkdir(parents=False, exist_ok=False)
        self._identity = source_identity
        self._failed = False
        self._closed = False
        self._sequence = 0
        self._bytes = 0
        self._artifact_hash = None
        self._published = None

    def _available(self):
        if self._failed or self._closed:
            raise ValueError('Capture unavailable after failure or closure')

    @staticmethod
    def _write(path, raw):
        with path.open('xb') as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())

    def _persist(self, result, owner_closed):
        manifest = dict(schema='nbsr-lab-local-capture-v1',
                        declared_source_identity=self._identity,
                        source_identity_verified=False, owner_closed=owner_closed,
                        ledger=result['ledger'])
        files = {'raw.bin': result['raw'],
                 'manifest.json': json.dumps(manifest, sort_keys=True, allow_nan=False).encode()}
        if result['artifact'] is not None:
            files['grouped.ndjson'] = result['artifact']
        size = sum(map(len, files.values()))
        if self._sequence >= MAX_SNAPSHOTS or self._bytes + size > (self._max_session_bytes if self._max_session_bytes is not None else MAX_SESSION_BYTES):
            raise ValueError('Capture persistence budget exhausted')
        sequence = self._sequence + 1
        pending = self._directory / f'.pending-{sequence:04d}'
        target = self._directory / f'snapshot-{sequence:04d}'
        pending.mkdir()
        for name, raw in files.items():
            self._write(pending / name, raw)
        # Same-parent rename publishes a complete bundle, never a partial file.
        # Incomplete pending evidence is intentionally retained on I/O failure.
        pending.rename(target)
        self._sequence = sequence
        self._bytes += size
        digest = result['ledger']['artifact_sha256']
        if digest is not None and digest != self._artifact_hash:
            self._published = target / 'grouped.ndjson'
            self._artifact_hash = digest
        return target

    def _failure(self):
        self._failed = True
        # Best effort only: a full disk can also prevent failure evidence writes.
        # Never mask the original error or turn it into success.
        try:
            self._write(self._directory / 'failure-raw.bin', self._parser.retained_raw)
        except OSError:
            pass

    def append(self, chunk, *, offset, source_identity):
        self._available()
        try:
            result = self._parser.append(chunk, offset=offset, source_identity=source_identity)
            return self._persist(result, False)
        except Exception:
            self._failure()
            raise

    def finish(self):
        self._available()
        try:
            result = self._persist(self._parser.finish(), True)
            self._closed = True
            return result
        except Exception:
            self._failure()
            raise

    def snapshot_path(self):
        if self._failed:
            raise ValueError('Capture unavailable after failure')
        return self._published
