"""Genera los iconos del panel (PNG, sin dependencias). Icono genérico: no describe la función.

Uso: python tools/make_icons.py   (escribe en static/icons/)
"""
from __future__ import annotations

import math
import struct
import zlib
from pathlib import Path

BG = (29, 78, 216)       # azul del botón principal
FG = (255, 255, 255)
SS = 4                   # supermuestreo para suavizar los bordes


def png(width: int, height: int, rgba: bytes) -> bytes:
    def chunk(tag: bytes, data: bytes) -> bytes:
        body = tag + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)

    raw = b"".join(b"\x00" + rgba[y * width * 4:(y + 1) * width * 4] for y in range(height))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def render(size: int, rounded: bool = True, glyph_scale: float = 1.0) -> bytes:
    """Cuadrado azul (con esquinas redondeadas) y un anillo blanco con un punto central."""
    n = size * SS
    c = n / 2
    r_out, r_in = n * 0.30 * glyph_scale, n * 0.21 * glyph_scale
    r_dot = n * 0.07 * glyph_scale
    radius = n * 0.22
    buf = bytearray(size * size * 4)
    for y in range(size):
        for x in range(size):
            acc = [0, 0, 0, 0]
            for sy in range(SS):
                for sx in range(SS):
                    px, py = x * SS + sx + 0.5, y * SS + sy + 0.5
                    inside = True
                    if rounded:
                        qx = abs(px - c) - (c - radius)
                        qy = abs(py - c) - (c - radius)
                        inside = not (qx > 0 and qy > 0 and math.hypot(qx, qy) > radius)
                    if not inside:
                        continue
                    d = math.hypot(px - c, py - c)
                    col = FG if (r_in <= d <= r_out or d <= r_dot) else BG
                    acc[0] += col[0]; acc[1] += col[1]; acc[2] += col[2]; acc[3] += 255
            cnt = SS * SS
            i = (y * size + x) * 4
            a = acc[3] // cnt
            if acc[3]:
                covered = acc[3] // 255  # muestras cubiertas: el color es el promedio de ellas
                buf[i:i + 3] = bytes(v // covered for v in acc[:3])
            buf[i + 3] = a
    return png(size, size, bytes(buf))


def main() -> None:
    out = Path(__file__).resolve().parent.parent / "static" / "icons"
    out.mkdir(parents=True, exist_ok=True)
    (out / "icon-192.png").write_bytes(render(192))
    (out / "icon-512.png").write_bytes(render(512))
    (out / "icon-maskable-512.png").write_bytes(render(512, rounded=False, glyph_scale=0.8))
    (out / "apple-touch-icon.png").write_bytes(render(180, rounded=False))  # iOS aplica su propio redondeo
    print("iconos generados en", out)


if __name__ == "__main__":
    main()
