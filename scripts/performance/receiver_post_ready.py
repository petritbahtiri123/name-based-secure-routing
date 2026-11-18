"""Offline integrity-bound post-ready handoff, not writer authentication."""
import hashlib
import os
from pathlib import Path
import stat
import time

from scripts.performance.reader_receipts import decode
from scripts.performance.reader_viewer_binding import attachment_arguments
from scripts.performance.receiver_observed_owner import ObservedReceiverOwner
from scripts.performance.viewer_owner_observation import ObservationSlot


class PostReady:
    """Read/revalidate exact bounded IPC; never publish or operate native handles.

    Canonical source and exclusive writer authority remain caller qualification
    gates. A hash here proves consistency, not who wrote the original bytes.
    """
    def __init__(self, root, run, owner, *, python, clock=time.monotonic, install=None):
        if type(owner) is not ObservedReceiverOwner:
            raise ValueError('original observed receiver owner required')
        self.owner, self.clock = owner, clock
        self.root = Path(root)
        self.run, self.python = run, python
        self.failed = False
        self.slot = None
        self.installed = False
        self.pins = {}
        self.previous = None
        try:
            if not self.root.is_absolute() or self.root != self.root.resolve():
                raise ValueError('canonical receiver root required')
            self.directory = self.root / 'live-lab' / 'receiver-command'
            request, self.pins['request.json'] = self._read('request.json', 8192)
            ready, self.pins['ready.json'] = self._read('ready.json', 1024)
            self.anchor = request.get('trial_anchor')
            attachment_arguments(self.root, run, request, ready, now=self._now(), python=python)
            expected = (python, '-B', str(self.root / 'cells' / 'baseline8' / 'bounded.py'),
                        'worker', str(self.directory / 'request.json'))
            if owner.argv != expected or owner.deadline != self.anchor + 173:
                raise ValueError('retained receiver owner/request mismatch')
            identity = (run, self.pins['request.json'][1], self.pins['ready.json'][1])
            self.slot = ObservationSlot(identity, anchor=self.anchor, deadline=self.anchor + 115)
            self.slot.bind_receiver(identity, anchor=self.anchor, deadline=self.anchor + 115, now=self._now())
            self.verify()
            if install is None:
                owner.install_observation(self.slot)
            else:
                install(owner, self.slot)
            self.installed = True
            self.verify()
        except BaseException:
            self.invalidate()
            raise

    def _now(self):
        import math
        now = self.clock()
        if (type(now) not in (int, float) or not math.isfinite(now)
                or (self.previous is not None and now < self.previous)):
            raise ValueError('post-ready clock uncertainty')
        self.previous = now
        return now

    def invalidate(self):
        self.failed = True
        self.owner.disable_observation()

    def _read(self, name, cap):
        path = self.directory / name
        for parent in (path.parent, *path.parent.parents):
            info = parent.lstat()
            if not stat.S_ISDIR(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 1024:
                raise ValueError('unsafe receiver IPC parent')
        def identity(info):
            if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > cap
                    or getattr(info, 'st_file_attributes', 0) & 1024):
                raise ValueError('unsafe receiver IPC file')
            return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns
        before = identity(path.lstat())
        with path.open('rb') as stream:
            opened = identity(os.fstat(stream.fileno()))
            if before[:4] != opened[:4]:
                raise ValueError('receiver IPC replaced')
            raw = stream.read(cap + 1)
            if len(raw) > cap or identity(os.fstat(stream.fileno())) != opened:
                raise ValueError('receiver IPC changed')
        if identity(path.lstat()) != before:
            raise ValueError('receiver IPC replaced')
        return decode(raw), (before, hashlib.sha256(raw).hexdigest())

    def verify(self):
        try:
            if self.failed or not self.anchor <= self._now() < self.anchor + 115:
                raise ValueError('original viewer window unavailable')
            if self.installed:
                self.owner.verify_observation(self.slot)
            for name, cap in (('request.json', 8192), ('ready.json', 1024)):
                _, pin = self._read(name, cap)
                if pin != self.pins[name]:
                    raise ValueError('receiver IPC pin changed')
            if self.installed:
                self.owner.verify_observation(self.slot)
            if not self.anchor <= self._now() < self.anchor + 115:
                raise ValueError('original viewer window expired')
        except BaseException:
            self.invalidate()
            raise
