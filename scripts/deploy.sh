#!/bin/bash
# Despliega services/<nombre> en la Raspberry. Uso: scripts/deploy.sh <nombre> [puerto]
# Si no se indica puerto se toma de la tabla de platform/PORTS.md.
set -euo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
N="${1:?uso: deploy.sh <nombre> [puerto]}"
load_host
need_key
need_sudo

[ -d "$ROOT/services/$N" ] || { echo "No existe services/$N" >&2; exit 1; }
for f in service.unit route.caddy; do
	[ -f "$ROOT/services/$N/deploy/$f" ] || { echo "Falta services/$N/deploy/$f" >&2; exit 1; }
done

PORT="${2:-$(awk -F'|' -v n="\`$N\`" '{gsub(/ /,"",$3); if ($3==n || index($3,n)==1) {gsub(/ /,"",$2); print $2; exit}}' "$ROOT/platform/PORTS.md")}"
[[ "$PORT" =~ ^[0-9]+$ ]] || { echo "Puerto no registrado en platform/PORTS.md" >&2; exit 1; }

tar czf - --exclude=.venv --exclude=__pycache__ --exclude=.pytest_cache --exclude=data-dev --exclude=tests -C "$ROOT/services" "$N" | ssh "${SSH_OPTS[@]}" "$PI_HOST" "cat > /tmp/rpo-$N.tgz"
ssh "${SSH_OPTS[@]}" "$PI_HOST" 'cat > /tmp/rpo-remote-install.sh' < "$ROOT/platform/remote-install.sh"
ssh "${SSH_OPTS[@]}" "$PI_HOST" "sudo bash /tmp/rpo-remote-install.sh '$N' '$PORT'; rc=\$?; rm -f /tmp/rpo-remote-install.sh; exit \$rc"
