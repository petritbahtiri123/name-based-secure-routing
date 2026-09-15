"""Failure-only metadata; call after children stop, before marker cleanup."""
import re
import stat
import time


MARKER = re.compile(r'(?:connection-[0-9]+\.(?:start|connected|active|release|ack)|destination-[0-9]+\.active)')


def snapshot_markers(directory):
    result = {'status': 'CAPTURED', 'scope': 'post-failure filesystem metadata; not transport-only latency',
              'captured_unix_ns': time.time_ns(), 'markers': []}
    try:
        for path in sorted(directory.iterdir()):
            if not MARKER.fullmatch(path.name):
                continue
            metadata = path.lstat()
            if stat.S_ISREG(metadata.st_mode):
                result['markers'].append({'name': path.name, 'mtime_ns': metadata.st_mtime_ns,
                                          'size_bytes': metadata.st_size})
    except OSError as error:
        result.update(status='UNAVAILABLE', error_type=type(error).__name__)
    return result
