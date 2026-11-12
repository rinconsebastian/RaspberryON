"""Monitor por ping (design D3). El `ping` real se inyecta para poder probar."""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Awaitable, Callable

from .power import PowerMachine

log = logging.getLogger("pc-power.monitor")

PingFn = Callable[[str], Awaitable[bool]]


async def system_ping(host: str, timeout_s: float = 3.0) -> bool:
    """Un ping ICMP con el binario del sistema. `host` ya fue validado como IP."""
    if os.name == "nt":  # solo desarrollo local
        args = ["ping", "-n", "1", "-w", "1000", host]
    else:
        args = ["ping", "-n", "-c", "1", "-W", "1", host]
    proc = await asyncio.create_subprocess_exec(
        *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL
    )
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), timeout_s)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        return False
    if proc.returncode != 0:
        return False
    # Windows devuelve 0 también con "host inaccesible"; exigir una respuesta real
    return os.name != "nt" or b"TTL=" in out


class Monitor:
    def __init__(self, host: str, interval_s: float, machine: PowerMachine, ping: PingFn = system_ping):
        self._host = host
        self._interval = interval_s
        self._machine = machine
        self._ping = ping

    async def step(self) -> bool:
        try:
            ok = await self._ping(self._host)
        except Exception:  # noqa: BLE001 - un fallo del ping cuenta como sin respuesta
            log.exception("error al ejecutar ping")
            ok = False
        self._machine.on_ping(ok)
        return ok

    async def run(self) -> None:
        while True:
            await self.step()
            await asyncio.sleep(self._interval)
