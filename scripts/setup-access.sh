#!/bin/bash
# Paso 1: acceso sin contraseña a la Raspberry (llave SSH + sudo sin contraseña).
# Es INTERACTIVO: te pedirá la contraseña de la Raspberry (una vez) y la de sudo (una vez).
# Es idempotente: si ya tienes acceso, no cambia nada.
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
load_host
need_cmd ssh; need_cmd scp

USER_NAME="${PI_HOST%@*}"
KEY="${SSH_KEY:-$HOME/.ssh/id_ed25519}"

say "Llave SSH de este equipo"
if [ ! -f "$KEY" ]; then
	mkdir -p "$(dirname "$KEY")"
	ssh-keygen -t ed25519 -f "$KEY" -N "" -C "raspberryon-$(hostname)" >/dev/null
	ok "llave creada en $KEY"
else
	ok "usando $KEY"
fi

say "Instalando la llave en $PI_HOST"
if pi true 2>/dev/null; then
	ok "ya entras por llave, no hace falta instalarla"
else
	echo "Te pedirá la contraseña de la Raspberry (la que pusiste en el Imager)."
	# StrictHostKeyChecking=accept-new: acepta la huella la primera vez, pero avisa si cambia después.
	ssh -o ConnectTimeout=10 -o StrictHostKeyChecking=accept-new "$PI_HOST" \
		'umask 077; mkdir -p ~/.ssh; touch ~/.ssh/authorized_keys; k=$(cat); grep -qxF "$k" ~/.ssh/authorized_keys || echo "$k" >> ~/.ssh/authorized_keys' \
		< "$KEY.pub" || die "No se pudo instalar la llave. Comprueba la IP, el usuario y la contraseña."
	pi true 2>/dev/null || die "La llave se copió pero el acceso sin contraseña no funciona (revisa permisos de ~/.ssh en la Raspberry)."
	ok "acceso por llave funcionando"
fi

say "sudo sin contraseña para $USER_NAME"
if pi 'sudo -n -k true' 2>/dev/null; then
	ok "ya tienes sudo sin contraseña"
else
	scp -o BatchMode=yes -o ConnectTimeout=10 "$ROOT/platform/enable-sudo.sh" "$PI_HOST:/tmp/enable-sudo.sh" >/dev/null \
		|| die "No pude copiar enable-sudo.sh a la Raspberry."
	echo "Ahora sudo te pedirá la contraseña de la cuenta (una sola vez)."
	ssh -t -o ConnectTimeout=10 "$PI_HOST" "sudo bash /tmp/enable-sudo.sh '$USER_NAME'; rc=\$?; rm -f /tmp/enable-sudo.sh; exit \$rc" \
		|| die "No se pudo activar sudo sin contraseña."
	pi 'sudo -n -k true' 2>/dev/null || die "sudo sigue pidiendo contraseña."
	ok "sudo sin contraseña activado"
fi

say "Acceso listo"
echo "Siguiente paso: bash scripts/provision.sh"
