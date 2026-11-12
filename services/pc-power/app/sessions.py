"""Sesiones en servidor persistidas en archivo (design D7).

Solo se guarda sha256(token), su expiración y una huella salada del código de
acceso vigente: al cambiar el código, las sesiones anteriores dejan de valer.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import time
from pathlib import Path
from typing import Callable


def _sha(data: str) -> str:
    return hashlib.sha256(data.encode()).hexdigest()


def code_matches(given: str, expected: str) -> bool:
    """Comparación en tiempo constante (sobre digests de longitud fija)."""
    return hmac.compare_digest(
        hashlib.sha256(given.encode()).digest(), hashlib.sha256(expected.encode()).digest()
    )


class SessionStore:
    def __init__(
        self,
        path: Path,
        access_code: str,
        days: int = 30,
        clock: Callable[[], float] = time.time,
    ):
        self._path = Path(path)
        self._code = access_code
        self._ttl = days * 86400
        self._clock = clock
        self._salt = ""
        self._sessions: dict[str, float] = {}
        self._load()

    # ---- API -----------------------------------------------------------
    def create(self) -> str:
        token = secrets.token_urlsafe(32)  # 256 bits
        self._sessions[_sha(token)] = self._clock() + self._ttl
        self._purge()
        self._save()
        return token

    def valid(self, token: str | None) -> bool:
        if not token:
            return False
        exp = self._sessions.get(_sha(token))
        if exp is None:
            return False
        if exp <= self._clock():
            self._purge()
            self._save()
            return False
        return True

    def revoke(self, token: str | None) -> None:
        if token and self._sessions.pop(_sha(token), None) is not None:
            self._save()

    def revoke_all(self) -> None:
        self._sessions.clear()
        self._save()

    def __len__(self) -> int:
        return len(self._sessions)

    # ---- persistencia ---------------------------------------------------
    def _fingerprint(self) -> str:
        return _sha(self._salt + self._code)

    def _load(self) -> None:
        data: dict = {}
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                data = {}
        except (OSError, ValueError):
            data = {}
        salt = data.get("salt")
        self._salt = salt if isinstance(salt, str) and salt else secrets.token_hex(16)
        if data.get("fingerprint") == self._fingerprint():
            now = self._clock()
            raw = data.get("sessions", {})
            if isinstance(raw, dict):
                self._sessions = {
                    k: float(v)
                    for k, v in raw.items()
                    if isinstance(k, str) and isinstance(v, (int, float)) and v > now
                }
        self._save()  # persiste la sal y descarta lo caducado o con otra huella

    def _purge(self) -> None:
        now = self._clock()
        self._sessions = {k: v for k, v in self._sessions.items() if v > now}

    def _save(self) -> None:
        payload = json.dumps(
            {"salt": self._salt, "fingerprint": self._fingerprint(), "sessions": self._sessions}
        )
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_name(self._path.name + ".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(payload)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, self._path)
