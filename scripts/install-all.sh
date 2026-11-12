#!/bin/bash
# Instalación completa en una Raspberry recién preparada, con un solo comando:
#
#     bash scripts/install-all.sh
#
# Encadena los pasos (se pueden repetir sin riesgo; lo ya hecho se salta o no cambia):
#   access     llave SSH + sudo sin contraseña         (te pide la contraseña de la Raspberry)
#   provision  Caddy, cortafuegos, SSH solo con llave, WiFi, actualizaciones
#   deploy     instala el servicio pc-power
#   configure  código de acceso, IP del PC, polaridad del relé, avisos
#   check      comprueba que todo está bien
#
# Para ejecutar solo algunos pasos:   bash scripts/install-all.sh configure check
# Antes de empezar: docs/DESPLIEGUE.md (preparar la SD, cablear el relé SIN conectarlo al PC).
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

case "${1:-}" in -h|--help) awk 'NR>1 && /^#/ {sub(/^# ?/,""); print; next} NR>1 {exit}' "${BASH_SOURCE[0]}"; exit 0 ;; esac

ALL=(access provision deploy configure check)
STEPS=("$@"); [ "${#STEPS[@]}" -gt 0 ] || STEPS=("${ALL[@]}")
for s in "${STEPS[@]}"; do
	[[ " ${ALL[*]} " == *" $s "* ]] || die "Paso desconocido: '$s'. Pasos válidos: ${ALL[*]}"
done
need_cmd ssh; need_cmd scp; need_cmd tar

# ---- ¿a qué Raspberry? ---------------------------------------------------------------------------
say "RaspberryON: instalación"
if [ -z "${PI_HOST:-}" ] && [ ! -f "$ROOT/.pi-host" ]; then
	echo "Escribe la dirección de la Raspberry como  usuario@ip  (el usuario que pusiste en el Imager)."
	echo "Ejemplo: pi@192.168.1.50   (la IP la ves en la lista de dispositivos de tu router)"
	read -r -p "Raspberry: " PI_HOST
	[[ "$PI_HOST" =~ ^[A-Za-z0-9._-]+@[A-Za-z0-9._-]+$ ]] || die "Formato no válido. Debe ser usuario@ip"
fi
load_host
if [ ! -f "$ROOT/.pi-host" ] || [ "$(tr -d '\r\n ' < "$ROOT/.pi-host")" != "$PI_HOST" ]; then
	printf '%s\n' "$PI_HOST" > "$ROOT/.pi-host"
	ok "Dirección guardada en .pi-host (no se versiona)"
fi
echo "  Raspberry:           $PI_HOST"
echo "  SSH permitido solo desde la red de este equipo (se calcula al aprovisionar)"
echo "  Pasos:               ${STEPS[*]}"
echo
confirm "¿Continuar?" || die "Cancelado."

run() { bash "$ROOT/scripts/$1" "${@:2}"; }
has() { [[ " ${STEPS[*]} " == *" $1 "* ]]; }

# ---- pasos -------------------------------------------------------------------------------------------
has access && run setup-access.sh
has provision && run provision.sh

if has deploy; then
	cat <<'TXT'

   IMPORTANTE (seguridad del PC): el relé debe estar cableado a la Raspberry pero SIN conectar
   todavía al pulsador de la placa base. Primero se prueba solo (docs/DESPLIEGUE.md, sección 7).
TXT
	say "Instalando el servicio pc-power"
	if ! run deploy.sh pc-power; then
		# Con la configuración aún vacía el servicio se niega a arrancar: es lo esperado la primera vez.
		if pi 'journalctl -u raspberryon-pc-power --no-pager -n 20 2>/dev/null' | grep -q "ERROR de configuración"; then
			warn "El servicio se instaló, pero espera su configuración (normal la primera vez). Sigue el siguiente paso."
		else
			pi 'journalctl -u raspberryon-pc-power --no-pager -n 15 2>/dev/null' | cut -c1-170 >&2 || true
			die "El despliegue falló por otra causa (mira el registro de arriba)."
		fi
	fi
fi

has configure && run configure.sh

if has check; then
	say "Comprobación final"
	run check.sh || warn "Hay fallos: revisa las líneas marcadas con XX y sus sugerencias."
fi

say "Hecho"
cat <<TXT
  Panel (desde tu red):   https://${PI_IP}/pc/      (el navegador avisará: certificado autofirmado)
  Siguientes pasos:       docs/DESPLIEGUE.md  ->  9 (conectar el relé al PC), 10 (acceso desde Internet), 11 (avisos)
  Diagnóstico en cualquier momento:  bash scripts/check.sh
TXT
