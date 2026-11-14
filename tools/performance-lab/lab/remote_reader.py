"""Standalone read-only bounded reader; launched ONLY by an owned supervisor.

One exact file, no glob, no subprocess, no workload signal or remote writes.
Outputs bounded prefix frames; identity authenticity comes from pinned SSH + plan.
"""
import argparse
import base64
import json
import os
import stat
import time

MAX_BYTES = 4 * 1024 * 1024

def read_prefix(path, state, limit=MAX_BYTES):
    before = os.lstat(path)
    if not stat.S_ISREG(before.st_mode):
        raise ValueError('Source is not a regular file')
    flags = os.O_RDONLY | getattr(os, 'O_BINARY', 0) | getattr(os, 'O_NOFOLLOW', 0)
    fd = os.open(path, flags)
    try:
        info = os.fstat(fd)
        identity = (info.st_dev, info.st_ino)
        if not stat.S_ISREG(info.st_mode) or identity != (before.st_dev, before.st_ino):
            raise ValueError('Source identity changed during open')
        if 'identity' in state and state['identity'] != identity:
            raise ValueError('Source replaced')
        if info.st_size > limit:
            raise ValueError('Source byte limit exceeded')
        # Freeze this observation length; concurrent append belongs to next poll.
        remaining = info.st_size
        chunks = []
        while remaining:
            chunk = os.read(fd, min(65536, remaining))
            if not chunk:
                raise ValueError('Source truncated during read')
            chunks.append(chunk); remaining -= len(chunk)
        raw = b''.join(chunks)
        after = os.lstat(path)
        if identity != (after.st_dev, after.st_ino) or not stat.S_ISREG(after.st_mode):
            raise ValueError('Source replaced during read')
        if not raw.startswith(state.get('prefix', b'')):
            raise ValueError('Source truncated or rewritten')
        state.update(identity=identity, prefix=raw)
        return raw
    finally:
        os.close(fd)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', required=True)
    parser.add_argument('--run', required=True)
    parser.add_argument('--seconds', type=int, required=True)
    parser.add_argument('--wire-bytes', type=int, required=True)
    args = parser.parse_args()
    if not os.path.isabs(args.source) or not 1 <= args.seconds <= 90:
        parser.error('Absolute source and lifetime 1..90 seconds required')
    if not args.run or len(args.run)>128 or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-' for c in args.run):
        parser.error('Invalid run identity')
    if not 1 <= args.wire_bytes <= MAX_BYTES:
        parser.error('Wire budget must be 1..4MiB')
    wire_bytes = 0
    def emit(row):
        nonlocal wire_bytes
        encoded = json.dumps(row)
        size = len(encoded.encode('utf-8'))+1
        if wire_bytes+size > args.wire_bytes:
            raise ValueError('Cumulative wire budget exceeded')
        print(encoded, flush=True)
        wire_bytes += size
    deadline = time.monotonic()+args.seconds
    state = {}; previous = None; sequence = 0
    emit(dict(schema='nbsr-lab-reader-start-v1', run=args.run, source=args.source,
              state='waiting-for-source', cadence_seconds=5, lifetime_seconds=args.seconds, wire_budget=args.wire_bytes))
    while time.monotonic() < deadline:
        try:
            raw = read_prefix(args.source, state)
        except FileNotFoundError:
            if state:
                raise ValueError('Source disappeared')
        else:
            if raw != previous:
                sequence += 1
                emit(dict(schema='nbsr-lab-prefix-v1', run=args.run,
                    source=args.source, sequence=sequence, file_identity=list(state['identity']),
                    prefix=base64.b64encode(raw).decode('ascii')))
                previous=raw
                # This marker controls only reader lifetime, not evidence validity.
                if raw.endswith(b'\n'):
                    try:
                        last = json.loads(raw.splitlines()[-1])
                    except (ValueError, IndexError):
                        last = {}
                    if isinstance(last, dict) and last.get('schema') == 'nbsr-b5-grouped-final-v1':
                        emit(dict(schema='nbsr-lab-reader-ended-v1', run=args.run,
                                  reason='source-final-observed', observations=sequence))
                        return
        time.sleep(min(5.0,max(0,deadline-time.monotonic())))
    # Lifetime expiry is NOT workload completion.
    emit(dict(schema='nbsr-lab-reader-ended-v1', run=args.run,
                          reason='bounded-lifetime-expired', observations=sequence))

if __name__ == '__main__':
    main()
