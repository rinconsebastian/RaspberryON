#!/bin/bash
# Copia de seguridad de la CONFIGURACIÓN de la Raspberry (para reinstalar o migrar sin perder nada):
#   - /etc/raspberryon/pc-power.env   (código de acceso, IP del PC, polaridad, avisos...)
#   - /etc/caddy/site.env y tls.caddy  (dominio / modo de certificado)
#   - historial y programaciones       (events.jsonl, schedule.json)
# NO copia las sesiones iniciadas (tendrás que volver a entrar con el código).
#
# Uso: bash scripts/backup.sh [carpeta_destino]       (por defecto: backups/AAAA-MM-DD_HHMM/)
# ATENCIÓN: la copia contiene el código de acceso en claro. Guárdala en un sitio privado.
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
load_host; need_cmd ssh; need_cmd tar; need_key; need_sudo

DEST="${1:-$ROOT/backups/$(date +%Y-%m-%d_%H%M)}"
[ -e "$DEST" ] && die "Ya existe $DEST (elige otra carpeta)."
mkdir -p "$DEST"
chmod 700 "$DEST" 2>/dev/null || true

say "Copiando la configuración de $PI_HOST a $DEST"
# --ignore-failed-read: si falta algún archivo opcional (p. ej. aún no hay historial) no se aborta
pi 'sudo tar czf - --ignore-failed-read -C / etc/raspberryon/pc-power.env etc/caddy/site.env etc/caddy/tls.caddy var/lib/raspberryon/pc-power/events.jsonl var/lib/raspberryon/pc-power/schedule.json 2>/dev/null' > "$DEST/config.tgz" \
	|| die "No se pudo crear la copia."
[ -s "$DEST/config.tgz" ] || die "La copia salió vacía."
listing="$(tar tzf "$DEST/config.tgz")"
[[ "$listing" == *etc/raspberryon/pc-power.env* ]] || die "La copia no contiene pc-power.env (¿está desplegado el servicio?)."
chmod 600 "$DEST/config.tgz" 2>/dev/null || true
echo "$PI_HOST" > "$DEST/origen.txt"

ok "Copia guardada: $DEST/config.tgz"
echo "Contenido:"; printf '%s\n' "$listing" | sed 's/^/  /'
warn "Contiene el código de acceso en claro: no la subas a ningún sitio público."
echo "Para restaurarla en una Raspberry nueva (ya desplegada): bash scripts/restore.sh \"$DEST\""
