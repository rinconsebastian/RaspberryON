#!/bin/bash
# Restaura una copia hecha con scripts/backup.sh en la Raspberry configurada (.pi-host / PI_HOST).
# Requisito: la Raspberry ya está aprovisionada y con el servicio desplegado
#   (bash scripts/provision.sh && bash scripts/deploy.sh pc-power).
# Uso: bash scripts/restore.sh <carpeta_de_la_copia> [--dry-run]
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

SRC="${1:-}"; DRY=0
[ -n "$SRC" ] || die "Uso: bash scripts/restore.sh <carpeta_de_la_copia> [--dry-run]"
[ "${2:-}" = "--dry-run" ] && DRY=1
[ -f "$SRC/config.tgz" ] || die "No encuentro $SRC/config.tgz (¿es una carpeta creada por backup.sh?)"
load_host; need_cmd ssh; need_cmd tar; need_key; need_sudo

say "Contenido de la copia"
listing="$(tar tzf "$SRC/config.tgz")"
printf '%s\n' "$listing" | sed 's/^/  /'
[[ "$listing" == *etc/raspberryon/pc-power.env* ]] || die "La copia no tiene pc-power.env."
pi 'test -f /etc/raspberryon/pc-power.env' || die "En $PI_HOST aún no existe el servicio. Despliégalo primero: bash scripts/deploy.sh pc-power"
if [ "$DRY" = 1 ]; then ok "--dry-run: no se ha modificado nada."; exit 0; fi

confirm "Se SOBRESCRIBIRÁ la configuración actual de $PI_HOST con la de la copia. ¿Continuar?" || die "Cancelado."

pi 'cat > /tmp/rpo-restore.tgz' < "$SRC/config.tgz"
pi 'bash -s' <<'REMOTE'
set -euo pipefail
T=$(mktemp -d); trap 'rm -rf "$T" /tmp/rpo-restore.tgz' EXIT
tar xzf /tmp/rpo-restore.tgz -C "$T"
sudo systemctl stop raspberryon-pc-power
if [ -f "$T/etc/raspberryon/pc-power.env" ]; then
	sudo install -m 0640 -o root -g svc-pc-power "$T/etc/raspberryon/pc-power.env" /etc/raspberryon/pc-power.env
fi
for f in site.env tls.caddy; do
	[ -f "$T/etc/caddy/$f" ] && sudo install -m 0644 -o root -g root "$T/etc/caddy/$f" "/etc/caddy/$f"
done
for f in events.jsonl schedule.json; do
	[ -f "$T/var/lib/raspberryon/pc-power/$f" ] && sudo install -m 0644 -o svc-pc-power -g svc-pc-power "$T/var/lib/raspberryon/pc-power/$f" "/var/lib/raspberryon/pc-power/$f"
done
sudo systemctl restart caddy
sudo systemctl start raspberryon-pc-power
sleep 8
echo "pc-power: $(systemctl is-active raspberryon-pc-power) | caddy: $(systemctl is-active caddy) | relé: $(pinctrl get 23 2>/dev/null | cut -c1-24)"
REMOTE
ok "Restaurado. Comprueba con: bash scripts/check.sh"
