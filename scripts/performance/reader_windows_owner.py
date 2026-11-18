"""Exact-handle owner promoted alone; no management/transport launch entrypoint."""

from scripts.performance.reader_windows_backend import RetainedJobError


class Unconfirmed(RuntimeError):
    """Exact ownership or cleanup could not be confirmed."""


class WindowsOwner:
    """Exact-handle job ownership adapter; never interpret leader exit as job exit.

    Backend calls must be bounded/nonblocking. Assignment failure leaves a suspended
    process outside the job, so that exact process is terminated explicitly. No
    breakaway or permission fallback is permitted. Failed closes keep their handles.
    """

    def __init__(self, argv, *, backend, cancel):
        self.argv, self.backend, self.cancel = tuple(argv), backend, cancel
        self.job = self.process = self.thread = None
        self.assigned = self.cancelled = self.killed = self.started = False

    @property
    def owned(self):
        return any(handle is not None for handle in (self.job, self.process, self.thread))

    def start(self):
        if self.started:
            raise Unconfirmed("owner already attempted")
        self.started = True
        try:
            self.job = self.backend.create_job()
        except RetainedJobError as exc:
            self.job = exc.job
            raise
        self.process, self.thread = self.backend.create_suspended(self.argv)
        self.backend.assign(self.job, self.process)
        self.assigned = True
        self.backend.resume(self.thread)

    def observe(self):
        if self.process is None:
            # A created job with no process still needs explicit handle closure.
            return 1, False
        code, active = self.backend.observe(self.job, self.process, self.assigned)
        if (code is not None and type(code) is not int) or type(active) is not int or active < 0:
            raise Unconfirmed("invalid job observation")
        # Job accounting may reach zero before the owned process is signalled
        # during asynchronous termination. Keep ownership pending until both
        # observations prove completion; callers retain their original deadline.
        return code, active != 0 or code is None

    def signal(self, name):
        if name in ("INT", "TERM"):
            if not self.cancelled:
                self.cancelled = True
                self.cancel()
        elif name == "KILL":
            if self.process is not None and not self.killed:
                self.killed = True
                self.backend.terminate(self.job, self.process, self.assigned)
        else:
            raise ValueError("unsupported ownership action")

    def reap(self):
        code, live = self.observe()
        if code is None or live:
            raise Unconfirmed("job or leader still owned")
        for name in ("thread", "process", "job"):
            handle = getattr(self, name)
            if handle is not None:
                self.backend.close(handle)
                setattr(self, name, None)
