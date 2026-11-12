#!/bin/bash
# Deja sudo sin contraseña para el usuario de administración.
# Se ejecuta UNA VEZ, EN LA RASPBERRY, de forma interactiva:
#
#   scp platform/enable-sudo.sh USUARIO@IP:/tmp/
#   ssh -t USUARIO@IP 'sudo bash /tmp/enable-sudo.sh USUARIO'
#
# (scripts/setup-access.sh hace esto por ti.)
#
# (sudo pedirá la contraseña de la cuenta; es la única vez.)
set -euo pipefail

USER_NAME="${1:-}"
[ -n "$USER_NAME" ] || { echo "uso: sudo bash enable-sudo.sh <usuario>" >&2; exit 2; }
id "$USER_NAME" >/dev/null 2>&1 || { echo "el usuario $USER_NAME no existe" >&2; exit 2; }
[ "$(id -u)" -eq 0 ] || { echo "ejecuta con sudo" >&2; exit 2; }

TARGET=/etc/sudoers.d/010-raspberryon-admin
TMP="$(mktemp)"
trap 'rm -f "$TMP"' EXIT

echo "$USER_NAME ALL=(ALL) NOPASSWD: ALL" > "$TMP"
chmod 0440 "$TMP"
visudo -cf "$TMP" >/dev/null
install -m 0440 -o root -g root "$TMP" "$TARGET"
visudo -c >/dev/null
echo "OK: $TARGET instalado para $USER_NAME"
