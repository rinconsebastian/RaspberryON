#!/bin/bash
# Paso 2: aprovisiona la Raspberry (Caddy, cortafuegos, SSH solo con llave, WiFi, actualizaciones).
# Requiere el paso 1 (scripts/setup-access.sh). Es idempotente: se puede repetir.
# Variables opcionales: PI_HOST=usuario@ip  LAN_CIDR=192.168.1.0/24 (red desde la que se permite SSH)
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
load_host
need_cmd ssh; need_cmd tar
need_key
need_sudo

# Red desde la que se permitirá SSH. Si no la fijaste tú, se toma la /24 de la IP desde la que este
# equipo se conecta, tal como la ve la Raspberry (así el cortafuegos nunca te deja fuera).
if [ -z "${LAN_CIDR_USER:-}" ]; then
	client_ip="$(pi 'echo "${SSH_CONNECTION%% *}"' 2>/dev/null || true)"
	if [[ "$client_ip" =~ ^([0-9]+\.[0-9]+\.[0-9]+)\.[0-9]+$ ]]; then
		LAN_CIDR="${BASH_REMATCH[1]}.0/24"
	else
		warn "No pude deducir tu red a partir de '$client_ip'; uso $LAN_CIDR. Si no coincide, fíjala: LAN_CIDR=192.168.1.0/24 bash scripts/provision.sh"
	fi
fi

say "Aprovisionando $PI_HOST (SSH permitido solo desde $LAN_CIDR)"
tar czf - -C "$ROOT" platform | pi 'rm -rf /tmp/rpo-platform && mkdir /tmp/rpo-platform && tar xzf - -C /tmp/rpo-platform'
# La conexión anterior autenticó por llave (BatchMode), por eso se puede endurecer SSH.
pi 'sudo env RPO_KEY_VERIFIED=1 RPO_ADMIN_USER="$USER" LAN_CIDR="'"$LAN_CIDR"'" bash /tmp/rpo-platform/platform/bootstrap.sh'
ok "Raspberry aprovisionada"
