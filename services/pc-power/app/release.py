"""Deja el relé en reposo (abierto) y termina.

Lo ejecuta systemd antes de arrancar el servicio (ExecStartPre) y cuando éste termina por
cualquier causa, incluido un `kill -9` (ExecStopPost). El núcleo no devuelve a entrada un pin
que murió como salida, así que sin este paso un fallo durante un pulso dejaría el relé cerrado.
"""
from __future__ import annotations

import os
import sys
from typing import Mapping

from .relay import GpioDriver


def release(env: Mapping[str, str] | None = None, lgpio_module=None) -> int:
    env = os.environ if env is None else env
    if env.get("RELAY_DRIVER", "gpio").strip().lower() == "mock":
        return 0
    polarity = env.get("RELAY_ACTIVE_HIGH", "").strip().lower()
    if polarity not in ("true", "false"):
        print("release: RELAY_ACTIVE_HIGH sin definir; no se toca el pin", file=sys.stderr)
        return 0
    try:
        pin = int(env.get("RELAY_GPIO", "").strip() or 23)
    except ValueError:
        print("release: RELAY_GPIO inválido", file=sys.stderr)
        return 1
    # El constructor deja el pin en su estado abierto; no se libera la línea después, para
    # que ese estado se conserve al terminar el proceso.
    GpioDriver(pin, polarity == "true", lgpio_module=lgpio_module)
    return 0


if __name__ == "__main__":
    raise SystemExit(release())
