#!/usr/bin/env python3
"""Actualiza un archivo de entorno (CLAVE=VALOR) sin tocar comentarios ni otras claves.

Se ejecuta EN la Raspberry, como root (lo lanza scripts/configure.sh):

    sudo python3 set-env.py /etc/raspberryon/pc-power.env  < instrucciones

Cada línea de la entrada estándar es una instrucción:
    CLAVE=VALOR   fija la clave (reemplaza la línea activa o añade una al final)
    -CLAVE        elimina la clave

Nunca imprime valores (pueden ser secretos). Escribe sobre el mismo archivo, de modo que
conserva su propietario y permisos.
"""
import re
import sys

KEY = re.compile(r"^[A-Z][A-Z0-9_]*$")


def apply(lines, instructions):
    out = list(lines)
    for ins in instructions:
        if ins.startswith("-"):
            key = ins[1:]
            if not KEY.match(key):
                raise ValueError(f"clave inválida: {key!r}")
            out = [l for l in out if not re.match(rf"^{key}=", l)]
            continue
        key, sep, value = ins.partition("=")
        if not sep or not KEY.match(key):
            raise ValueError(f"instrucción inválida (clave {key!r})")
        if "\n" in value or "\r" in value:
            raise ValueError(f"valor inválido para {key}")
        new = f"{key}={value}"
        for i, l in enumerate(out):
            if re.match(rf"^{key}=", l):
                out[i] = new
                break
        else:
            out.append(new)
    return out


def main() -> int:
    if len(sys.argv) != 2:
        print("uso: set-env.py <archivo>  < instrucciones", file=sys.stderr)
        return 2
    path = sys.argv[1]
    instructions = [l.rstrip("\r\n") for l in sys.stdin if l.strip()]
    try:
        with open(path, encoding="utf-8") as f:
            lines = f.read().splitlines()
    except FileNotFoundError:
        print(f"no existe {path} (despliega primero el servicio)", file=sys.stderr)
        return 1
    try:
        out = apply(lines, instructions)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    with open(path, "w", encoding="utf-8") as f:  # mismo inodo: se conservan dueño y permisos
        f.write("\n".join(out).rstrip("\n") + "\n")
    print(f"{len(instructions)} instrucción(es) aplicada(s) a {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
