from __future__ import annotations

import heapq
from collections import deque
from collections.abc import Callable
from threading import RLock
from time import monotonic


class NameRouteRateLimited(Exception):
    """Anonymous name-route admission exceeded a configured bounded rate."""


class AdmissionLimiter:
    def __init__(
        self,
        *,
        global_limit: int,
        client_limit: int,
        max_clients: int,
        window_seconds: float = 60.0,
        clock: Callable[[], float] = monotonic,
    ):
        if min(global_limit, client_limit, max_clients) <= 0 or window_seconds <= 0:
            raise ValueError("Admission limits must be positive")
        self._global_limit = global_limit
        self._client_limit = client_limit
        self._max_clients = max_clients
        self._window_seconds = window_seconds
        self._clock = clock
        self._global: deque[float] = deque()
        self._clients: dict[str, deque[float]] = {}
        self._expirations: list[tuple[float, str]] = []
        self._lock = RLock()

    def consume(self, client_id: str) -> None:
        if not isinstance(client_id, str) or not client_id:
            raise ValueError("Admission client ID is required")
        now = self._clock()
        cutoff = now - self._window_seconds
        with self._lock:
            while self._global and self._global[0] <= cutoff:
                self._global.popleft()
            self._expire_clients(now, cutoff)
            client_events = self._clients.get(client_id)
            if client_events is None:
                if len(self._clients) >= self._max_clients:
                    raise NameRouteRateLimited("Name-route client capacity exceeded")
                client_events = deque()
                self._clients[client_id] = client_events
            while client_events and client_events[0] <= cutoff:
                client_events.popleft()
            if len(self._global) >= self._global_limit or len(client_events) >= self._client_limit:
                if not client_events:
                    self._clients.pop(client_id, None)
                raise NameRouteRateLimited("Name-route request rate exceeded")
            self._global.append(now)
            client_events.append(now)
            heapq.heappush(self._expirations, (now + self._window_seconds, client_id))

    def _expire_clients(self, now: float, cutoff: float) -> None:
        while self._expirations and self._expirations[0][0] <= now:
            _, client_id = heapq.heappop(self._expirations)
            events = self._clients.get(client_id)
            if events is None:
                continue
            while events and events[0] <= cutoff:
                events.popleft()
            if not events:
                del self._clients[client_id]
