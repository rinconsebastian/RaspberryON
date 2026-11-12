"""Limitación silenciosa de intentos de código (design D8)."""
from __future__ import annotations

import ipaddress
import time
from collections import deque
from typing import Callable

LOCAL_PEERS = {"127.0.0.1", "::1"}


def client_ip(peer: str | None, forwarded_for: str | None) -> str:
    """IP del cliente. X-Forwarded-For solo se respeta si el par es el proxy local."""
    peer = peer or "unknown"
    if peer in LOCAL_PEERS and forwarded_for:
        first = forwarded_for.split(",")[0].strip()
        try:
            return str(ipaddress.ip_address(first))
        except ValueError:
            pass
    return peer


class AttemptLimiter:
    def __init__(
        self,
        ip_max: int = 5,
        ip_window_s: float = 15 * 60,
        global_max: int = 30,
        global_window_s: float = 60 * 60,
        clock: Callable[[], float] = time.monotonic,
    ):
        self._ip_max, self._ip_win = ip_max, ip_window_s
        self._g_max, self._g_win = global_max, global_window_s
        self._clock = clock
        self._by_ip: dict[str, deque[float]] = {}
        self._global: deque[float] = deque()

    @property
    def ip_max(self) -> int:
        return self._ip_max

    def _trim(self, dq: deque[float], window: float, now: float) -> None:
        while dq and now - dq[0] >= window:
            dq.popleft()

    def _ip_count(self, ip: str, now: float) -> int:
        dq = self._by_ip.get(ip)
        if dq is None:
            return 0
        self._trim(dq, self._ip_win, now)
        if not dq:
            del self._by_ip[ip]
            return 0
        return len(dq)

    def ip_blocked(self, ip: str) -> bool:
        return self._ip_count(ip, self._clock()) >= self._ip_max

    def global_blocked(self) -> bool:
        now = self._clock()
        self._trim(self._global, self._g_win, now)
        return len(self._global) >= self._g_max

    def blocked(self, ip: str) -> bool:
        return self.ip_blocked(ip) or self.global_blocked()

    def record_failure(self, ip: str) -> bool:
        """Registra un fallo. Devuelve True si con él esta IP queda bloqueada."""
        now = self._clock()
        self._by_ip.setdefault(ip, deque()).append(now)
        self._global.append(now)
        return self._ip_count(ip, now) == self._ip_max
