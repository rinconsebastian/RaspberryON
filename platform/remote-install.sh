#!/bin/bash
# Instala un servicio en la Raspberry. Lo invoca scripts/deploy.sh vía sudo.
# Uso: remote-install.sh <nombre> <puerto>   (espera /tmp/rpo-<nombre>.tgz)
set -euo pipefail

N="${1:?nombre}"; PORT="${2:?puerto}"
[[ "$N" =~ ^[a-z][a-z0-9-]{0,24}$ ]] || { echo "nombre inválido" >&2; exit 2; }
[[ "$PORT" =~ ^[0-9]+$ ]] || { echo "puerto inválido" >&2; exit 2; }

TGZ="/tmp/rpo-$N.tgz"
DEST="/opt/raspberryon/$N"
STAGE="/opt/raspberryon/.$N.new"
ENVF="/etc/raspberryon/$N.env"

id -u "svc-$N" >/dev/null 2>&1 || useradd --system --no-create-home --shell /usr/sbin/nologin "svc-$N"

rm -rf "$STAGE"; mkdir -p "$STAGE"
tar xzf "$TGZ" -C "$STAGE" --strip-components=1
rm -f "$TGZ"

# Sustituir marcadores en los archivos de despliegue
for f in "$STAGE"/deploy/*; do
	[ -f "$f" ] && sed -i "s/@NAME@/$N/g; s/@PORT@/$PORT/g" "$f"
done

# Conservar venv entre despliegues
[ -d "$DEST/venv" ] && mv "$DEST/venv" "$STAGE/venv"
rm -rf "$DEST"; mv "$STAGE" "$DEST"
chown -R root:root "$DEST"
chmod -R go-w "$DEST"
[ -d "$DEST/venv" ] && chmod -R a+rX "$DEST/venv" || true

# Grupos extra del servicio (p. ej. gpio), uno por línea en deploy/groups
if [ -f "$DEST/deploy/groups" ]; then
	while read -r g; do
		[ -n "$g" ] && usermod -aG "$g" "svc-$N"
	done < "$DEST/deploy/groups"
fi

[ -f "$DEST/deploy/install.sh" ] && (cd "$DEST" && bash ./deploy/install.sh)

# .env: solo si no existe (no se sobrescriben secretos)
if [ ! -f "$ENVF" ] && [ -f "$DEST/deploy/env.example" ]; then
	install -m 0640 -o root -g "svc-$N" "$DEST/deploy/env.example" "$ENVF"
fi

install -m 0644 "$DEST/deploy/service.unit" "/etc/systemd/system/raspberryon-$N.service"
install -m 0644 "$DEST/deploy/route.caddy" "/etc/caddy/conf.d/$N.caddy"

systemctl daemon-reload
systemctl enable "raspberryon-$N" >/dev/null 2>&1
systemctl restart "raspberryon-$N"

(set -a; . /etc/caddy/site.env; set +a; caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile >/dev/null)
systemctl reload caddy

sleep 6  # un servicio con configuración inválida tarda unos segundos en fallar
STATE="$(systemctl is-active "raspberryon-$N" || true)"
echo "raspberryon-$N: $STATE"
[ "$STATE" = "active" ]
