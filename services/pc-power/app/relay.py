"""Relé del pulsador de encendido: pulsos seguros (design D2).

Garantías: el relé arranca abierto, nunca queda cerrado fuera de un pulso
(try/finally), y solo se admite un pulso a la vez más 5 s de enfriamiento.
"""
from __future__ import annotations

import asyncio
import time
from typing import Awaitable, Callable, Protocol


class RelayBusy(Exception):
    """Hay un pulso en curso o en enfriamiento."""


class RelayDriver(Protocol):
    def on(self) -> None: ...
    def off(self) -> None: ...
    def close(self) -> None: ...


class MockDriver:
    """Registra los cambios con su instante; para pruebas y desarrollo."""

    def __init__(self, clock: Callable[[], float] = time.monotonic):
        self._clock = clock
        self.energized = False  # True = relé cerrado (pulsando); False = abierto (reposo)
        self.events: list[tuple[float, str]] = []

    def on(self) -> None:
        self.energized = True
        self.events.append((self._clock(), "on"))

    def off(self) -> None:
        self.energized = False
        self.events.append((self._clock(), "off"))

    def close(self) -> None:
        self.off()


class GpioDriver:
    """Relé en un GPIO usando lgpio directamente (sin gpiozero).

    Módulo activo en BAJO ("colector abierto"): cerrado = salida en bajo; abierto = entrada
    (alta impedancia). Los módulos de 5 V con entrada activa en bajo no se apagan de forma
    fiable con un 3,3 V *manejado* en alto: solo se sueltan dejando el pin flotar.
    Módulo activo en ALTO: cerrado = salida en alto; abierto = salida en bajo.
    Si el proceso muere, el núcleo libera la línea y queda como entrada (abierto).
    """

    def __init__(self, pin: int, active_high: bool, lgpio_module=None, chip: int = 0):
        if lgpio_module is None:
            import lgpio as lgpio_module  # importación tardía: solo existe en la Pi
        self._lg = lgpio_module
        self._pin = pin
        self._active_high = active_high
        self._h = self._lg.gpiochip_open(chip)
        self._open_relay()  # estado de reposo antes de cualquier otra cosa

    def _free(self) -> None:
        try:
            self._lg.gpio_free(self._h, self._pin)
        except Exception:  # noqa: BLE001 - línea sin reclamar
            pass

    def _open_relay(self) -> None:
        self._free()
        if self._active_high:
            self._lg.gpio_claim_output(self._h, self._pin, 0, 0)
        else:
            self._lg.gpio_claim_input(self._h, self._pin, getattr(self._lg, "SET_BIAS_DISABLE", 0))

    def on(self) -> None:
        self._free()
        self._lg.gpio_claim_output(self._h, self._pin, 0, 1 if self._active_high else 0)

    def off(self) -> None:
        self._open_relay()

    def close(self) -> None:
        try:
            self._open_relay()
        finally:
            self._free()
            self._lg.gpiochip_close(self._h)


class Relay:
    def __init__(
        self,
        driver: RelayDriver,
        cooldown_s: float = 5.0,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ):
        self._driver = driver
        self._cooldown = cooldown_s
        self._clock = clock
        self._sleep = sleep
        self._active = False
        self._cooldown_until = 0.0

    @property
    def active(self) -> bool:
        """Pulso en curso."""
        return self._active

    @property
    def busy(self) -> bool:
        """Pulso en curso o dentro del enfriamiento posterior."""
        return self._active or self._clock() < self._cooldown_until

    def retry_after(self) -> float:
        return max(0.0, self._cooldown_until - self._clock())

    def start(self, seconds: float) -> "asyncio.Task[None]":
        """Inicia un pulso. Síncrono: la comprobación de ocupado y la reserva son
        atómicas, de modo que dos peticiones simultáneas nunca pulsan dos veces."""
        if self.busy:
            raise RelayBusy()
        self._active = True
        task = asyncio.ensure_future(self._run(seconds))
        task.add_done_callback(self._finish)
        return task

    async def pulse(self, seconds: float) -> None:
        await self.start(seconds)

    async def _run(self, seconds: float) -> None:
        try:
            self._driver.on()
            await self._sleep(seconds)
        finally:
            self._driver.off()  # siempre abrir, incluso ante excepción o cancelación

    def _finish(self, task: "asyncio.Task[None]") -> None:
        # También se ejecuta si la tarea se cancela antes de arrancar.
        self._active = False
        self._cooldown_until = self._clock() + self._cooldown

    def close(self) -> None:
        self._driver.close()
