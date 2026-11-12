#!/bin/bash
# Paso 4: configura el servicio pc-power en la Raspberry (código de acceso, IP del PC, polaridad
# del relé, avisos) y lo reinicia. Requiere haber desplegado antes (scripts/deploy.sh pc-power).
#
# Uso interactivo:      bash scripts/configure.sh
# Solo mostrar cambios: bash scripts/configure.sh --dry-run
# Sin preguntas (automatizar), con variables de entorno:
#   ACCESS_CODE=... PC_HOST=192.168.1.50 RELAY_ACTIVE_HIGH=false \
#   [NTFY_URL=https://ntfy.sh/tema] [PUBLIC_URL=https://mi-dominio:puerto] [TZ=..] [PC_NAME=..] \
#   bash scripts/configure.sh --yes
#
# Lo que dejes en blanco se conserva. En NTFY_URL / PUBLIC_URL, escribe "-" para quitarlos.
# El código de acceso nunca se muestra ni viaja como argumento de un comando.
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

DRY=0
for a in "$@"; do
	case "$a" in
		--dry-run) DRY=1 ;;
		--yes|-y) YES=1 ;;
		-h|--help) awk 'NR>1 && /^#/ {sub(/^# ?/,""); print; next} NR>1 {exit}' "${BASH_SOURCE[0]}"; exit 0 ;;
		*) die "Opción desconocida: $a (usa --help)" ;;
	esac
done

load_host; need_cmd ssh; need_key; need_sudo
ENVF=/etc/raspberryon/pc-power.env
TTY=0; [ -t 0 ] && TTY=1

current="$(pi "sudo cat $ENVF" 2>/dev/null || true)"
[ -n "$current" ] || die "Aún no existe $ENVF en la Raspberry. Despliega primero: bash scripts/deploy.sh pc-power"
cur() { printf '%s\n' "$current" | sed -n "s/^$1=//p" | head -1 | tr -d '\r'; }

valid_ipv4() { [[ "$1" =~ ^([0-9]{1,3})\.([0-9]{1,3})\.([0-9]{1,3})\.([0-9]{1,3})$ ]] && for o in 1 2 3 4; do [ "${BASH_REMATCH[$o]}" -le 255 ] || return 1; done; }

# ask NOMBRE "pregunta" "valor_actual" [secreto]  -> deja el resultado en la variable REPLY_VAL
ask() {
	local name="$1" prompt="$2" curval="$3" secret="${4:-}" val
	val="${!name:-}"  # ¿viene por variable de entorno?
	if [ -z "$val" ] && [ "$TTY" = 1 ] && [ "${YES:-0}" != "1" ]; then
		if [ -n "$secret" ]; then read -r -s -p "$prompt" val; echo; else read -r -p "$prompt" val; fi
	fi
	REPLY_VAL="$val"
}

lines=()          # instrucciones CLAVE=VALOR / -CLAVE para set-env.py
summary=()

# ---- IP del PC ----------------------------------------------------------------------------------
c_host="$(cur PC_HOST)"
ask PC_HOST "IP del PC que se controla [${c_host:-sin definir}]: " "$c_host"
host="${REPLY_VAL:-$c_host}"
[ -n "$host" ] || die "Falta la IP del PC (PC_HOST)."
valid_ipv4 "$host" || die "PC_HOST no es una IP válida: $host"
if [ "$host" != "$c_host" ]; then lines+=("PC_HOST=$host"); summary+=("PC_HOST        = $host"); else summary+=("PC_HOST        = $host (sin cambios)"); fi

# ---- polaridad del relé -------------------------------------------------------------------------
c_pol="$(cur RELAY_ACTIVE_HIGH)"
if [ -z "${RELAY_ACTIVE_HIGH:-}" ] && [ "$TTY" = 1 ] && [ "${YES:-0}" != "1" ]; then
	cat <<'TXT'

Polaridad del módulo de relé:
  1) ACTIVO EN BAJO  -> el relé cierra cuando el pin está en bajo (lo habitual en módulos de 5 V
                        con optoacoplador, y el caso de la instalación original).
  2) ACTIVO EN ALTO  -> el relé cierra cuando el pin está en alto.
  Si no lo sabes: haz la prueba de la guía (docs/DESPLIEGUE.md, sección 7) con el relé DESCONECTADO del PC.
TXT
	read -r -p "Elige 1 o 2 [${c_pol:+actual: $c_pol}]: " choice
	case "$choice" in 1) RELAY_ACTIVE_HIGH=false ;; 2) RELAY_ACTIVE_HIGH=true ;; "") RELAY_ACTIVE_HIGH="" ;; *) die "Opción no válida" ;; esac
fi
pol="${RELAY_ACTIVE_HIGH:-$c_pol}"
[[ "$pol" == "true" || "$pol" == "false" ]] || die "RELAY_ACTIVE_HIGH debe ser true o false (ahora: '${pol}')."
if [ "$pol" != "$c_pol" ]; then lines+=("RELAY_ACTIVE_HIGH=$pol"); summary+=("RELAY_ACTIVE_HIGH = $pol"); else summary+=("RELAY_ACTIVE_HIGH = $pol (sin cambios)"); fi

# ---- código de acceso -----------------------------------------------------------------------------
c_code_len="$(cur ACCESS_CODE | awk '{print length($0)}')"
code="${ACCESS_CODE:-}"
if [ -z "$code" ] && [ "$TTY" = 1 ] && [ "${YES:-0}" != "1" ]; then
	echo
	echo "Código de acceso (lo pedirá la web). Mínimo 8 caracteres; se recomiendan 12 o más, con letras."
	[ "${c_code_len:-0}" -ge 8 ] && echo "(Enter = conservar el actual)"
	read -r -s -p "Código: " code; echo
	if [ -n "$code" ]; then
		read -r -s -p "Repítelo: " code2; echo
		[ "$code" = "$code2" ] || die "Los dos códigos no coinciden."
	fi
fi
if [ -n "$code" ]; then
	[ "${#code}" -ge 8 ] || die "El código debe tener al menos 8 caracteres."
	[[ "$code" != *$'\n'* ]] || die "El código no puede tener saltos de línea."
	[[ "$code" =~ ^[0-9]+$ ]] && warn "Tu código solo tiene dígitos: es más fácil de adivinar. Se recomiendan letras y 12+ caracteres."
	[ "${#code}" -lt 12 ] && warn "Tu código tiene ${#code} caracteres; se recomiendan 12 o más."
	lines+=("ACCESS_CODE=$code"); summary+=("ACCESS_CODE    = (nuevo, ${#code} caracteres)")
else
	[ "${c_code_len:-0}" -ge 8 ] || die "Falta el código de acceso (mínimo 8 caracteres)."
	summary+=("ACCESS_CODE    = (sin cambios, ${c_code_len} caracteres)")
fi

# ---- opcionales ---------------------------------------------------------------------------------------
optional() { # NOMBRE "pregunta" regex "ejemplo"
	local name="$1" prompt="$2" re="$3" example="$4" c val
	c="$(cur "$name")"
	ask "$name" "$prompt [${c:-vacío}]: " "$c"
	val="${REPLY_VAL}"
	if [ -z "$val" ]; then summary+=("$name = ${c:-(vacío)} (sin cambios)"); return; fi
	if [ "$val" = "-" ]; then lines+=("-$name"); summary+=("$name = (se quita)"); return; fi
	val="${val%/}"
	[[ "$val" =~ $re ]] || die "$name no es válida. Ejemplo: $example"
	if [ "$val" != "$c" ]; then lines+=("$name=$val"); summary+=("$name = $val"); else summary+=("$name = $val (sin cambios)"); fi
}
echo
optional NTFY_URL "Avisos al móvil: URL del tema de ntfy (Enter = conservar, - = quitar)" '^https?://[^/]+/[^/]+$' "https://ntfy.sh/pc-<texto-largo-aleatorio>"
optional PUBLIC_URL "Dirección pública para los botones del aviso, solo esquema y host (Enter = conservar, - = quitar)" '^https?://[^/]+$' "https://mi-dominio.duckdns.org"

# TZ y PC_NAME solo se aplican si se pasan como variables de entorno
for k in TZ PC_NAME; do
	v="${!k:-}"
	if [ -n "$v" ]; then
		[[ "$v" != *$'\n'* ]] || die "$k inválido"
		[ "$v" != "$(cur "$k")" ] && { lines+=("$k=$v"); summary+=("$k = $v"); }
	fi
done

echo; say "Cambios para $PI_HOST"
printf '  %s\n' "${summary[@]}"
if [ "${#lines[@]}" -eq 0 ]; then ok "No hay nada que cambiar."; [ "$DRY" = 1 ] && exit 0; fi
if [ "$DRY" = 1 ]; then echo; ok "--dry-run: no se ha modificado nada."; exit 0; fi

if [ "${#lines[@]}" -gt 0 ]; then
	confirm "¿Aplicar y reiniciar el servicio?" || die "Cancelado; no se cambió nada."
	pi 'cat > /tmp/rpo-set-env.py' < "$ROOT/platform/set-env.py"
	printf '%s\n' "${lines[@]}" | pi "sudo python3 /tmp/rpo-set-env.py $ENVF; rc=\$?; rm -f /tmp/rpo-set-env.py; exit \$rc" >/dev/null \
		|| die "No se pudo escribir la configuración."
	ok "Configuración escrita"
fi

say "Reiniciando el servicio"
pi 'sudo systemctl restart raspberryon-pc-power; sleep 8; echo "estado: $(systemctl is-active raspberryon-pc-power)"; echo "relé (GPIO23): $(pinctrl get 23 2>/dev/null | cut -c1-24)"'
if ! pi 'systemctl is-active --quiet raspberryon-pc-power'; then
	pi 'journalctl -u raspberryon-pc-power --no-pager -n 8' | cut -c1-170 >&2 || true
	die "El servicio no arrancó. Revisa el mensaje de arriba (suele ser un valor inválido en la configuración)."
fi
ok "Servicio activo"
echo "Comprueba todo con: bash scripts/check.sh"
