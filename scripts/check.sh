#!/bin/bash
# Paso 5 (y herramienta de diagnóstico): comprueba que todo el sistema está bien.
# Es de SOLO LECTURA: no cambia nada ni acciona el relé. Nunca muestra secretos.
#   OK = bien   !! = revisar (no impide funcionar)   XX = falla (hay que arreglarlo)
# Termina con código 1 si hay algún XX.
set -uo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
load_host; need_cmd ssh; need_key; need_sudo

P=0; W=0; F=0
pass() { P=$((P+1)); printf '\033[1;32m  OK\033[0m  %s\n' "$*"; }
warnc() { W=$((W+1)); printf '\033[1;33m  !!\033[0m  %s\n' "$1"; [ -n "${2:-}" ] && printf '        -> %s\n' "$2"; return 0; }
fail() { F=$((F+1)); printf '\033[1;31m  XX\033[0m  %s\n' "$1"; [ -n "${2:-}" ] && printf '        -> %s\n' "$2"; }
section() { printf '\n\033[1m%s\033[0m\n' "$*"; }

REMOTE='
ENVF=/etc/raspberryon/pc-power.env
envv() { sudo -n sed -n "s/^$1=//p" "$ENVF" 2>/dev/null | head -1 | tr -d "\r"; }
echo "os=$(. /etc/os-release; echo "$PRETTY_NAME")"
for s in caddy ufw unattended-upgrades raspberryon-pc-power raspberryon-wifi-powersave; do
  echo "act_$s=$(systemctl is-active $s 2>/dev/null)"; echo "en_$s=$(systemctl is-enabled $s 2>/dev/null)"
done
echo "wlan=$(ip link show wlan0 >/dev/null 2>&1 && echo yes || echo no)"
echo "ufw_80=$(sudo -n ufw status 2>/dev/null | grep -c "^80/tcp .*ALLOW")"
echo "ufw_443=$(sudo -n ufw status 2>/dev/null | grep -c "^443/tcp .*ALLOW")"
echo "ufw_22_any=$(sudo -n ufw status 2>/dev/null | grep -E "^22(/tcp)? " | grep -c "Anywhere")"
echo "ssh_pw=$(sudo -n sshd -T 2>/dev/null | awk "/^passwordauthentication/{print \$2}")"
GPIO=$(envv RELAY_GPIO); GPIO=${GPIO:-23}
for i in 1 2 3; do echo "pin$i=$(pinctrl get $GPIO 2>/dev/null | awk "{print \$2, \$5}")"; sleep 0.5; done
echo "code_len=$(envv ACCESS_CODE | awk "{print length(\$0)}")"
echo "pc_host=$(envv PC_HOST)"; echo "polarity=$(envv RELAY_ACTIVE_HIGH)"
echo "ntfy=$(envv NTFY_URL)"; echo "public_url=$(envv PUBLIC_URL)"; echo "tz=$(envv TZ)"
PCH=$(envv PC_HOST)
[ -n "$PCH" ] && { ping -c 2 -W 1 "$PCH" >/dev/null 2>&1 && echo "pc_ping=up" || echo "pc_ping=down"; }
echo "ntp=$(timedatectl show -p NTPSynchronized --value 2>/dev/null)"
echo "disk=$(df / --output=pcent 2>/dev/null | tail -1 | tr -dc 0-9)"
echo "mem=$(awk "/MemAvailable/{print int(\$2/1024)}" /proc/meminfo)"
echo "temp=$(vcgencmd measure_temp 2>/dev/null | tr -dc 0-9.)"
echo "throttled=$(vcgencmd get_throttled 2>/dev/null | cut -d= -f2)"
echo "uptime=$(uptime -p)"
echo "errors=$(journalctl -u raspberryon-pc-power -p err --since "1 hour ago" --no-pager 2>/dev/null | grep -vc "^-- ")"
echo "web_pc=$(curl -sk -m 6 -o /dev/null -w "%{http_code}" https://127.0.0.1/pc/)"
echo "web_root=$(curl -sk -m 6 -o /dev/null -w "%{http_code}/%{size_download}" https://127.0.0.1/)"
echo "web_api=$(curl -sk -m 6 -o /dev/null -w "%{http_code}" https://127.0.0.1/pc/api/status)"
echo "web_http=$(curl -s -m 6 -o /dev/null -w "%{http_code}" http://127.0.0.1/pc/)"
NT=$(envv NTFY_URL); [ -n "$NT" ] && echo "ntfy_net=$(curl -s -m 6 -o /dev/null -w "%{http_code}" "$(echo "$NT" | sed "s#^\(https\?://[^/]*\)/.*#\1/#")")"
'
say "Revisando $PI_HOST ..."
facts="$(printf '%s\n' "$REMOTE" | pi 'bash -s' 2>/dev/null)" || die "No pude leer el estado de la Raspberry."
g() { printf '%s\n' "$facts" | sed -n "s/^$1=//p" | head -1; }

section "Sistema"
echo "  $(g os) | $(g uptime)"
[ "$(g ntp)" = "yes" ] && pass "Reloj sincronizado por NTP" || warnc "El reloj NO está sincronizado" "Las programaciones dependen de la hora: comprueba la conexión a Internet (timedatectl)."
d="$(g disk)"; [ "${d:-0}" -lt 90 ] && pass "Disco al ${d}%" || warnc "Disco al ${d}%" "Libera espacio en la tarjeta SD."
m="$(g mem)"; [ "${m:-0}" -ge 100 ] && pass "Memoria libre: ${m} MB" || warnc "Poca memoria libre: ${m} MB"
t="$(g temp)"; if [ -n "$t" ]; then awk "BEGIN{exit !($t < 80)}" && pass "Temperatura ${t} C" || warnc "Temperatura alta: ${t} C" "Mejora la ventilación."; fi
th="$(g throttled)"; if [ -n "$th" ]; then [ "$th" = "0x0" ] && pass "Alimentación estable" || warnc "La Raspberry registró subvoltaje o limitación ($th)" "Usa una fuente de 5 V / 2,5 A o más y un buen cable."; fi

section "Seguridad de la Raspberry"
[ "$(g act_ufw)" = "active" ] && [ "$(g ufw_80)" -ge 1 ] && [ "$(g ufw_443)" -ge 1 ] && pass "Cortafuegos activo (80 y 443 abiertos)" || fail "Cortafuegos mal configurado" "Ejecuta: bash scripts/provision.sh"
[ "$(g ufw_22_any)" = "0" ] && pass "SSH solo desde la red local" || warnc "El puerto SSH está abierto a cualquier origen" "Ejecuta: bash scripts/provision.sh"
[ "$(g ssh_pw)" = "no" ] && pass "SSH solo con llave (contraseña desactivada)" || warnc "SSH acepta contraseña" "Ejecuta: bash scripts/provision.sh (solo la desactiva si tu llave funciona)"
[ "$(g en_unattended-upgrades)" = "enabled" ] && pass "Actualizaciones de seguridad automáticas" || warnc "Actualizaciones automáticas desactivadas" "Ejecuta: bash scripts/provision.sh"
if [ "$(g wlan)" = "yes" ]; then [ "$(g act_raspberryon-wifi-powersave)" = "active" ] && pass "WiFi sin ahorro de energía" || warnc "WiFi con ahorro de energía (puede cortar la conexión)" "Ejecuta: bash scripts/provision.sh"; fi

section "Servicios"
[ "$(g act_caddy)" = "active" ] && [ "$(g en_caddy)" = "enabled" ] && pass "Caddy activo y habilitado" || fail "Caddy no está activo" "sudo systemctl status caddy (en la Raspberry); o: bash scripts/provision.sh"
if [ "$(g act_raspberryon-pc-power)" = "active" ]; then pass "Servicio pc-power activo"
else fail "El servicio pc-power NO está activo" "journalctl -u raspberryon-pc-power -n 20 (en la Raspberry). Si dice 'ERROR de configuración': bash scripts/configure.sh"; fi
[ "$(g en_raspberryon-pc-power)" = "enabled" ] && pass "pc-power arranca solo al encender" || warnc "pc-power no arranca solo" "bash scripts/deploy.sh pc-power"
e="$(g errors)"; [ "${e:-0}" -eq 0 ] && pass "Sin errores del servicio en la última hora" || warnc "$e línea(s) de error en la última hora" "journalctl -u raspberryon-pc-power -p err (en la Raspberry)"

section "Relé"
p1="$(g pin1)"; p2="$(g pin2)"; p3="$(g pin3)"; pol="$(g polarity)"
if [[ "$p1" == ip* || "$p1" == "ip "* ]] && [[ "$p2" == ip* ]] && [[ "$p3" == ip* ]]; then
	pass "Relé ABIERTO (pin como entrada, en reposo)"
elif [ "$pol" = "false" ] && [[ "$p1" == op* && "$p2" == op* && "$p3" == op* ]] && [[ "$p1 $p2 $p3" != *hi* ]]; then
	fail "El relé parece CERRADO de forma continua (equivale a mantener pulsado el botón del PC)" "Para el servicio: ssh $PI_HOST 'sudo systemctl stop raspberryon-pc-power; pinctrl set 23 ip'  y revisa la polaridad (bash scripts/configure.sh)."
else
	warnc "Estado del pin del relé: $p1 | $p2 | $p3" "Si hay una acción en curso es normal; repite la comprobación en unos segundos."
fi

section "Configuración"
cl="$(g code_len)"
if [ "${cl:-0}" -ge 12 ]; then pass "Código de acceso: ${cl} caracteres"
elif [ "${cl:-0}" -ge 8 ]; then warnc "Código de acceso corto (${cl} caracteres)" "Se recomiendan 12 o más antes de abrirlo a Internet: bash scripts/configure.sh"
else fail "Falta el código de acceso (o tiene menos de 8 caracteres)" "bash scripts/configure.sh"; fi
[ -n "$(g pc_host)" ] && pass "IP del PC controlado: $(g pc_host)" || fail "Falta la IP del PC" "bash scripts/configure.sh"
[[ "$pol" == "true" || "$pol" == "false" ]] && pass "Polaridad del relé definida (activo en alto: $pol)" || fail "Falta la polaridad del relé" "bash scripts/configure.sh"
[ -n "$(g tz)" ] && echo "  Zona horaria del servicio: $(g tz)" || echo "  Zona horaria del servicio: America/Bogota (por defecto)"
[ -n "$(g ntfy)" ] && pass "Avisos ntfy configurados" || echo "  Avisos ntfy: no configurados (opcional)"
[ -n "$(g public_url)" ] && echo "  Dirección pública: $(g public_url)" || echo "  Dirección pública: no configurada (el recordatorio saldrá sin botones)"

section "PC controlado"
case "$(g pc_ping)" in
	up) pass "El PC responde a ping (la web lo mostrará ENCENDIDO)" ;;
	down) warnc "El PC no responde a ping (la web lo mostrará APAGADO)" "Si en realidad está encendido: permite ICMP en su firewall (README del servicio) y comprueba la IP." ;;
	*) warnc "Sin IP del PC para probar" ;;
esac

section "Web"
[ "$(g web_pc)" = "200" ] && pass "https://<ip>/pc/ responde (200)" || fail "La web no responde por HTTPS (código $(g web_pc))" "Mira los servicios de arriba; sudo systemctl status caddy raspberryon-pc-power"
[ "$(g web_root)" = "404/0" ] && pass "La raíz devuelve 404 vacío (no revela nada)" || warnc "La raíz no devuelve 404 vacío ($(g web_root))"
[ "$(g web_api)" = "404" ] && pass "La API sin sesión da 404" || warnc "La API sin sesión devuelve $(g web_api) (se esperaba 404)"
[ "$(g web_http)" = "301" ] || [ "$(g web_http)" = "308" ] && pass "HTTP (puerto 80) redirige a HTTPS" || warnc "El puerto 80 devuelve $(g web_http) (se esperaba una redirección)"
if code="$(curl -sk -m 8 -o /dev/null -w '%{http_code}' "https://$PI_IP/pc/" 2>/dev/null)" && [ "$code" = "200" ]; then pass "Desde este equipo, https://$PI_IP/pc/ funciona"; else warnc "Desde este equipo no se llega a https://$PI_IP/pc/ (código ${code:-?})" "Comprueba que estás en la misma red que la Raspberry."; fi

if [ -n "$(g ntfy)" ]; then
	section "Avisos"
	[ "$(g ntfy_net)" = "200" ] && pass "La Raspberry llega al servidor ntfy" || warnc "La Raspberry no llega al servidor ntfy (código $(g ntfy_net))" "Comprueba su salida a Internet."
fi
if [ -n "$(g public_url)" ]; then
	section "Acceso desde Internet"
	out="$(curl -s -m 10 -o /dev/null -w '%{http_code} %{ssl_verify_result}' "$(g public_url)/pc/" 2>/dev/null || true)"
	code="${out%% *}"; ver="${out##* }"
	if [ "$code" = "200" ]; then
		pass "$(g public_url)/pc/ responde (200)"
		[ "$ver" = "0" ] && pass "Certificado válido para este equipo" || warnc "Certificado NO verificado por este equipo (código ${ver:-?})" "Si usas certificado autofirmado, los botones de ntfy no funcionarán (ver docs/DESPLIEGUE.md, sección 10)."
	else
		warnc "No se llega a $(g public_url)/pc/ (código ${code:-?})" "Revisa el reenvío de puertos / proxy inverso. Desde dentro de la LAN puede fallar sin 'NAT loopback'."
	fi
fi

echo; printf '\033[1mResumen:\033[0m %d correctos, %d avisos, %d fallos\n' "$P" "$W" "$F"
[ "$F" -eq 0 ] && exit 0 || exit 1
