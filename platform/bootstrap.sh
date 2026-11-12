#!/bin/bash
# Aprovisionamiento idempotente de la Raspberry. Se ejecuta EN la Raspberry, como root,
# desde scripts/provision.sh. Variables opcionales:
#   LAN_CIDR           red local desde la que se permite SSH (la pasa scripts/provision.sh)
#   RPO_KEY_VERIFIED   =1 si la sesión que lanza esto autenticó con llave (habilita endurecer SSH)
#   RPO_ADMIN_USER     usuario cuyo authorized_keys se comprueba
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
LAN_CIDR="${LAN_CIDR:?falta LAN_CIDR (ejecuta scripts/provision.sh)}"
ADMIN="${RPO_ADMIN_USER:-${SUDO_USER:-}}"
export DEBIAN_FRONTEND=noninteractive

[ "$(id -u)" -eq 0 ] || { echo "ejecuta como root" >&2; exit 2; }

say() { echo "==> $*"; }

# --- Paquetes -------------------------------------------------------------
say "Paquetes"
need=()
for p in caddy ufw unattended-upgrades iw; do
	dpkg -s "$p" >/dev/null 2>&1 || need+=("$p")
done
if [ "${#need[@]}" -gt 0 ]; then
	apt-get update -qq
	apt-get install -y -qq "${need[@]}"
fi

# --- Directorios -----------------------------------------------------------
say "Directorios"
install -d -m 0755 /opt/raspberryon /etc/caddy/conf.d
install -d -m 0755 /etc/raspberryon
[ -f /etc/caddy/site.env ] || printf '# Sin SITE_ADDRESS => :443 con certificado autofirmado.\n# Con dominio: SITE_ADDRESS=mi-dominio.duckdns.org (y vaciar /etc/caddy/tls.caddy)\n#SITE_ADDRESS=\n' > /etc/caddy/site.env
[ -f /etc/caddy/tls.caddy ] || printf 'tls internal {\n\ton_demand\n}\n' > /etc/caddy/tls.caddy

# --- Caddy -----------------------------------------------------------------
say "Caddy"
install -d /etc/systemd/system/caddy.service.d
printf '[Service]\nEnvironmentFile=-/etc/caddy/site.env\n' > /etc/systemd/system/caddy.service.d/10-raspberryon.conf
if ! cmp -s "$HERE/Caddyfile" /etc/caddy/Caddyfile; then
	[ -f /etc/caddy/Caddyfile.orig ] || cp -a /etc/caddy/Caddyfile /etc/caddy/Caddyfile.orig
	install -m 0644 "$HERE/Caddyfile" /etc/caddy/Caddyfile
fi
systemctl daemon-reload
systemctl enable caddy >/dev/null 2>&1
# SITE_ADDRESS vacío: validar con valor por defecto
(set -a; . /etc/caddy/site.env; set +a; caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile >/dev/null)
systemctl restart caddy

# --- journald --------------------------------------------------------------
say "journald"
install -d /etc/systemd/journald.conf.d
printf '[Journal]\nSystemMaxUse=50M\n' > /etc/systemd/journald.conf.d/raspberryon.conf
systemctl restart systemd-journald

# --- Cortafuegos -----------------------------------------------------------
say "ufw"
ufw default deny incoming >/dev/null
ufw default allow outgoing >/dev/null
ufw allow 80/tcp >/dev/null
ufw allow 443/tcp >/dev/null
ufw allow from "$LAN_CIDR" to any port 22 proto tcp >/dev/null
ufw --force enable >/dev/null

# --- SSH solo con llave ----------------------------------------------------
say "SSH"
if [ "${RPO_KEY_VERIFIED:-0}" = "1" ] && [ -n "$ADMIN" ] \
	&& [ -s "$(getent passwd "$ADMIN" | cut -d: -f6)/.ssh/authorized_keys" ]; then
	[ -f /etc/ssh/sshd_config.bak ] || cp -a /etc/ssh/sshd_config /etc/ssh/sshd_config.bak
	install -d /etc/ssh/sshd_config.d
	printf 'PasswordAuthentication no\nKbdInteractiveAuthentication no\n' > /etc/ssh/sshd_config.d/10-raspberryon.conf
	if sshd -t; then
		systemctl reload ssh
		echo "SSH: autenticación por contraseña desactivada"
	else
		rm -f /etc/ssh/sshd_config.d/10-raspberryon.conf
		echo "SSH: configuración inválida, cambio revertido" >&2
		exit 1
	fi
else
	echo "SSH: no se verificó acceso por llave; la contraseña sigue habilitada"
fi

# --- WiFi sin ahorro de energía -------------------------------------------
say "WiFi power save"
if ip link show wlan0 >/dev/null 2>&1; then
	cat > /etc/systemd/system/raspberryon-wifi-powersave.service <<'EOF'
[Unit]
Description=Desactivar ahorro de energía de wlan0
After=network.target sys-subsystem-net-devices-wlan0.device
Wants=sys-subsystem-net-devices-wlan0.device

[Service]
Type=oneshot
ExecStart=/usr/sbin/iw dev wlan0 set power_save off
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
EOF
	systemctl daemon-reload
	systemctl enable raspberryon-wifi-powersave >/dev/null 2>&1
	systemctl restart raspberryon-wifi-powersave
fi

# --- Actualizaciones automáticas ------------------------------------------
say "unattended-upgrades"
printf 'APT::Periodic::Update-Package-Lists "1";\nAPT::Periodic::Unattended-Upgrade "1";\n' > /etc/apt/apt.conf.d/20auto-upgrades
systemctl enable --now unattended-upgrades >/dev/null 2>&1 || true

say "Listo"
