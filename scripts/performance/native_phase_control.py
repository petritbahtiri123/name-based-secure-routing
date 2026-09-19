"""Bounded loopback-only adapter for existing benchmark counter phase hooks.

An ACK confirms marker submission, not packet capture. The complete capture
must independently prove marker coverage and order before accepting accounting.
"""

import socket
import threading
import time

from scripts.analyze_b1_v2_capture import PHASE_NAMES


class PhaseControl:
    def __init__(self, emit):
        self.emit = emit
        self.transitions = []
        self.error = None
        self.stopping = threading.Event()

    @property
    def completed(self):
        return len(self.transitions) == len(PHASE_NAMES) and self.error is None

    def __enter__(self):
        self.listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            self.listener.bind(('127.0.0.1', 0))
            self.listener.listen(1)
            self.listener.settimeout(.1)
            self.endpoint = self.listener.getsockname()
            self.thread = threading.Thread(target=self._serve, name='native-phase-control')
            self.thread.start()
        except BaseException:
            self.listener.close()
            raise
        return self

    def _serve(self):
        while not self.stopping.is_set():
            try:
                connection, _ = self.listener.accept()
            except socket.timeout:
                continue
            with connection:
                connection.settimeout(.2)
                try:
                    line = bytearray()
                    deadline = time.monotonic() + 1
                    while not line.endswith(b'\n'):
                        if self.stopping.is_set() or time.monotonic() >= deadline:
                            raise ValueError('phase message deadline')
                        try:
                            chunk = connection.recv(129 - len(line))
                        except socket.timeout:
                            continue
                        if not chunk:
                            raise ValueError('incomplete phase message')
                        line.extend(chunk)
                        if len(line) > 128:
                            raise ValueError('phase message exceeds bound')
                    index = len(self.transitions)
                    if index >= len(PHASE_NAMES) or line != (PHASE_NAMES[index] + '\n').encode():
                        raise ValueError('unexpected phase transition')
                    name = PHASE_NAMES[index]
                    self.emit(name)
                    self.transitions.append(dict(phase=name, monotonic_ns=time.monotonic_ns()))
                    connection.sendall(b'{"status":"ok"}\n')
                except Exception as error:
                    self.error = str(error)
                    try:
                        connection.sendall(b'{"status":"error"}\n')
                    except OSError:
                        pass
                    return

    def __exit__(self, exc_type, exc_value, traceback):
        self.stopping.set()
        self.thread.join(timeout=2)
        self.listener.close()
        if self.thread.is_alive():
            raise RuntimeError('phase control did not stop')
        if exc_type is None and not self.completed:
            raise ValueError(self.error or 'incomplete phase transitions')
