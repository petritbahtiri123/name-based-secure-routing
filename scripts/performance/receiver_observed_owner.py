"""Source-only receiver monitor adapter, not wired into any launcher."""
import threading

from scripts.performance.reader_windows_drain import DrainingOwner
from scripts.performance.viewer_owner_observation import ObservationSlot


class ObservedReceiverOwner(DrainingOwner):
    """Reuse the original monitor's retained owner; never publish or do file I/O.

    A future receiver-only constructor call must still pass through the existing
    finite_receiver.retain_owner thread/identity check. This class does not bind
    request/readiness files, authenticate callers, or qualify a native run.
    """
    def __init__(self, argv, *, observation, **kwargs):
        if observation is not None and type(observation) is not ObservationSlot:
            raise ValueError('fixed in-memory observation slot required')
        self._monitor = threading.get_ident()
        self._observation = observation
        self._observation_lock = threading.Lock()
        self._observation_generation = 0
        self._observation_terminal = False
        self._observation_installed = observation is not None
        self.observation_error = None
        super().__init__(argv, **kwargs)

    def _same_thread(self):
        if threading.get_ident() != self._monitor:
            self.disable_observation()
            raise RuntimeError('native operations belong to the original monitor')

    def start(self):
        self._same_thread()
        try:
            return super().start()
        except BaseException:
            self.disable_observation()
            raise

    def disable_observation(self):
        """Control-plane safe: memory only, no native signals or file operations."""
        with self._observation_lock:
            self._observation_terminal = True
            self._observation_generation += 1
            if self._observation is not None:
                self._observation.revoke()

    def install_observation(self, slot):
        """Install once after integrity-bound readiness; no native operation."""
        with self._observation_lock:
            try:
                if (type(slot) is not ObservationSlot or self._observation_terminal
                        or self._observation_installed or not self.started or not self.assigned or not self.owned):
                    raise ValueError('observation installation unavailable')
                slot.consume_receiver_binding()
                self._observation = slot
                self._observation_installed = True
                self._observation_generation += 1
            except BaseException:
                self._observation_terminal = True
                self._observation_generation += 1
                if self._observation is not None:
                    self._observation.revoke()
                if type(slot) is ObservationSlot:
                    slot.revoke()
                raise

    def verify_observation(self, slot):
        with self._observation_lock:
            if self._observation_terminal or not self._observation_installed or slot is not self._observation:
                raise ValueError('receiver observation no longer installed')

    def observe(self):
        self._same_thread()
        with self._observation_lock:
            slot = self._observation
            generation = self._observation_generation
        sequence = None
        if slot is not None:
            try:
                sequence = slot.pending(now=self.clock())
            except Exception as error:
                self.observation_error = self.observation_error or type(error).__name__[:64]
                self.disable_observation()
        try:
            result = super().observe()
        except BaseException:
            self.disable_observation()
            raise
        if result != (None, True) or self.cancelled or self.killed or self.drain_failure or self.drain_until is not None:
            self.disable_observation()
            return result
        try:
            with self._observation_lock:
                if (not self._observation_terminal and slot is self._observation
                        and generation == self._observation_generation and sequence is not None):
                    slot.answer(sequence, owned=True, now=self.previous)
        except Exception as error:
            self.observation_error = self.observation_error or type(error).__name__[:64]
            self.disable_observation()
        return result

    def signal(self, name):
        self._same_thread()
        self.disable_observation()
        return super().signal(name)

    def reap(self):
        self._same_thread()
        self.disable_observation()
        return super().reap()
