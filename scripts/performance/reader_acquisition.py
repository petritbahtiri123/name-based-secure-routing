"""OFFLINE v2: transport closure and final capture precede settlement. No transport adapter."""

import threading
import time


class Acquisition:
    def __init__(self, reader, poll, *, clock=time.monotonic, interval=5.0, whole=115.0, ready_budget=15.0):
        if not (0 < interval <= 5 and 0 < whole <= 175 and 0 < ready_budget <= 15):
            raise ValueError("fixed lifecycle bounds")
        self.reader, self.poll, self.clock = reader, poll, clock
        self.interval, self.whole, self.ready_budget = interval, whole, ready_budget
        self.started = None
        self.reader_finished = None
        self.reader_value = None
        self.done = threading.Event()
        self.transport_closed = threading.Event()
        self.ready = threading.Event()
        self.errors = []
        self.lock = threading.Lock()
        self.owner_thread = self.pump_thread = None

    def error(self, where, exc):
        with self.lock:
            self.errors.append({"stage": where, "type": type(exc).__name__, "message": str(exc)[:512]})

    def _reader(self):
        try:
            self.reader_value = self.reader()
        except BaseException as exc:
            self.error("owned_reader", exc)
        finally:
            self.reader_finished = self.clock()
            if self.reader_finished >= self.started + self.whole:
                self.error("reader_deadline", TimeoutError("original acquisition deadline"))
            self.transport_closed.set()
            self.done.set()

    def _pump(self):
        try:
            while not self.transport_closed.is_set():
                state = self.poll(final=False)
                if state.get("ready") is True:
                    self.ready.set()
                if state.get("error"):
                    raise RuntimeError(state["error"])
                self.transport_closed.wait(self.interval)
            state = self.poll(final=True)
            if state.get("ready") is True:
                self.ready.set()
            if state.get("error"):
                raise RuntimeError(state["error"])
        except BaseException as exc:
            self.error("bridge", exc)

    def start(self, *, wait_ready=True):
        if self.started is not None:
            raise RuntimeError("one use only")
        self.started = self.clock()
        self.owner_thread = threading.Thread(target=self._reader, name="nbsr-owned-readonly-reader", daemon=False)
        self.pump_thread = threading.Thread(target=self._pump, name="nbsr-local-frame-pump", daemon=False)
        try:
            self.pump_thread.start()
            self.owner_thread.start()
        except BaseException as exc:
            self.error("thread_start", exc)
            self.transport_closed.set()
            self.done.set()
            raise
        if not wait_ready:
            return
        try:
            while not self.ready.is_set():
                if self.errors or self.done.is_set():
                    raise RuntimeError("reader failed before ready")
                remaining = self.started + self.ready_budget - self.clock()
                if remaining <= 0:
                    raise TimeoutError("reader readiness before PRE expired")
                self.ready.wait(min(0.05, remaining))
            if self.errors:
                raise RuntimeError("reader/bridge readiness failed")
        except BaseException as exc:
            self.error("readiness", exc)
            raise

    def finish(self, post_started=None):
        if self.started is None:
            return {"status": "NOT_STARTED"}
        deadline = self.started + self.whole
        for name, t in (("reader", self.owner_thread), ("pump", self.pump_thread)):
            if t is not None and t.ident is not None:
                t.join(max(0, deadline - self.clock()))
                if t.is_alive():
                    self.error(name, TimeoutError("owned acquisition join unresolved"))
        if self.clock() >= deadline:
            self.error("finish_deadline", TimeoutError("original acquisition deadline"))
        joined = all(t is None or t.ident is None or not t.is_alive() for t in (self.owner_thread, self.pump_thread))
        before_post = type(post_started) in (int, float) and self.reader_finished is not None and self.reader_finished <= post_started
        return {
            "status": "LOCAL_READER_JOINED" if joined and not self.errors else "INVALID_ACQUISITION",
            "joined": joined,
            "errors": list(self.errors),
            "started": self.started,
            "reader_finished": self.reader_finished,
            "reader_value": self.reader_value,
            "reader_finished_by_post_start": before_post,
            "timing_scope": "retrospective; does not prove observer had no effect; no POST wait",
            "immediate_cancellation_supported": False,
        }

    def close_capture(self):
        """Trusted exact-owner closure hook ONLY, never an external proof parser.

        Caller must have observed success/empty group, reaped all handles and validated
        cancellation/drain state. No post permission exists until this final pump join
        succeeds and the immutable final capture is validated by the caller.
        """
        if self.started is None or self.transport_closed.is_set():
            raise RuntimeError("one started closure only")
        self.transport_closed.set()
        t = self.pump_thread
        if t is None or t.ident is None or t is threading.current_thread():
            raise RuntimeError("final pump ownership missing")
        remaining = self.started + self.whole - self.clock()
        if remaining <= 0:
            raise TimeoutError("original capture deadline")
        t.join(remaining)
        if t.is_alive():
            self.error("capture_join", TimeoutError("final pump unresolved"))
            raise TimeoutError("final pump unresolved")
        if self.clock() >= self.started + self.whole:
            raise TimeoutError("original capture deadline")
        if self.errors:
            raise RuntimeError("final capture failed")
