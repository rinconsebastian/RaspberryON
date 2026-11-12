#!/bin/bash
# Retira un servicio de la Raspberry. Uso: scripts/remove.sh <nombre>
set -euo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
N="${1:?uso: remove.sh <nombre>}"
[[ "$N" =~ ^[a-z][a-z0-9-]{0,24}$ ]] || { echo "nombre inválido" >&2; exit 2; }
load_host
need_key

ssh -o BatchMode=yes "$PI_HOST" "sudo bash -s" <<EOF
set -u
N='$N'
systemctl disable --now "raspberryon-\$N" 2>/dev/null
rm -f "/etc/systemd/system/raspberryon-\$N.service" "/etc/caddy/conf.d/\$N.caddy"
systemctl daemon-reload
(set -a; . /etc/caddy/site.env; set +a; caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile >/dev/null) && systemctl reload caddy
id -u "svc-\$N" >/dev/null 2>&1 && userdel "svc-\$N"
rm -rf "/opt/raspberryon/\$N" "/etc/raspberryon/\$N.env" "/var/lib/raspberryon/\$N"
echo "servicio \$N retirado"
EOF
