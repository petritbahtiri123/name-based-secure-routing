"""Catchable benchmark-controller cancellation at explicit ownership safe points."""

import signal


class Cancellation:
    """Defer catchable signals to safe points, including across Popen assignment.

    Raising directly in a signal handler can lose ownership of a just-spawned
    child before Popen returns. Recording a request also lets finally cleanup
    finish when another signal arrives. SIGKILL cannot be handled.
    """

    def __init__(self):
        self.requested = None
        self.previous = {}

    def request(self, number, frame):
        self.requested = number

    def check(self):
        if self.requested is not None:
            raise InterruptedError('benchmark controller cancelled by ' + signal.Signals(self.requested).name)

    def __enter__(self):
        for name in ('SIGINT', 'SIGTERM', 'SIGHUP'):
            if hasattr(signal, name):
                number = getattr(signal, name)
                self.previous[number] = signal.signal(number, self.request)
        return self

    def __exit__(self, *_):
        for number, handler in self.previous.items():
            signal.signal(number, handler)


def not_cancelled():
    pass
