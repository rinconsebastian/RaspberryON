#!/bin/bash
# Funciones comunes de los scripts. Se carga con:  source "$(dirname "$0")/lib.sh"
#
# La Raspberry a la que se conectan los scripts se resuelve así (el primero que exista):
#   1. variable de entorno PI_HOST         (p. ej. PI_HOST=pi@192.168.1.50)
#   2. archivo .pi-host en la raíz del repo (lo crea scripts/install-all.sh; no se versiona)

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SSH_OPTS=(-o BatchMode=yes -o ConnectTimeout=10)

say()  { printf '\n\033[1;34m==>\033[0m %s\n' "$*"; }
ok()   { printf '\033[1;32m  OK\033[0m  %s\n' "$*"; }
warn() { printf '\033[1;33m  !!\033[0m  %s\n' "$*" >&2; }
die()  { printf '\033[1;31m  XX\033[0m  %s\n' "$*" >&2; exit 1; }

# Fija PI_HOST (usuario@ip), PI_IP y LAN_CIDR. LAN_CIDR es la red desde la que se permitirá SSH:
# aquí es solo una estimación (la /24 de la Raspberry); scripts/provision.sh la calcula con la IP
# desde la que se conecta ESTE equipo, para no dejarte fuera. LAN_CIDR_USER recuerda si la fijaste tú.
load_host() {
	LAN_CIDR_USER="${LAN_CIDR:-}"
	if [ -z "${PI_HOST:-}" ] && [ -f "$ROOT/.pi-host" ]; then
		PI_HOST="$(tr -d '\r\n ' < "$ROOT/.pi-host")"
	fi
	[ -n "${PI_HOST:-}" ] || die "No sé a qué Raspberry conectar. Ejecuta scripts/install-all.sh o define PI_HOST=usuario@ip"
	[[ "$PI_HOST" == *@* ]] || die "PI_HOST debe tener la forma usuario@ip (ahora: $PI_HOST)"
	PI_IP="${PI_HOST#*@}"
	if [ -z "${LAN_CIDR:-}" ] && [[ "$PI_IP" =~ ^([0-9]+\.[0-9]+\.[0-9]+)\.[0-9]+$ ]]; then
		LAN_CIDR="${BASH_REMATCH[1]}.0/24"
	fi
	: "${LAN_CIDR:=192.168.0.0/24}"
	export PI_HOST PI_IP LAN_CIDR
}

# Ejecuta un comando en la Raspberry sin pedir contraseña (usa la llave SSH).
pi() { ssh "${SSH_OPTS[@]}" "$PI_HOST" "$@"; }

need_key() {
	pi true 2>/dev/null || die "No puedo entrar a $PI_HOST con la llave SSH. Ejecuta primero: bash scripts/setup-access.sh"
}

need_sudo() {
	pi 'sudo -n true' 2>/dev/null || die "sudo pide contraseña en la Raspberry. Ejecuta primero: bash scripts/setup-access.sh"
}

# ¿Hay un comando en el PC?
need_cmd() { command -v "$1" >/dev/null 2>&1 || die "Falta '$1' en este equipo (instala Git for Windows / OpenSSH)."; }

# Pregunta sí/no (por defecto: no). Con YES=1 responde que sí sin preguntar.
confirm() {
	[ "${YES:-0}" = "1" ] && return 0
	local a
	read -r -p "$1 [s/N] " a
	[[ "$a" =~ ^[sSyY]$ ]]
}
