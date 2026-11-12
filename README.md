# RaspberryON

Plataforma para alojar servicios web en una Raspberry Pi (Debian 13, arm64) detrás de un único punto de entrada HTTPS (Caddy). Cada servicio es una unidad systemd con usuario propio, escucha solo en `127.0.0.1` y se publica bajo un prefijo de ruta (`/pc/`, `/otro/`…).

> **¿Empiezas con una Raspberry nueva? Sigue la [guía de despliegue desde cero](docs/DESPLIEGUE.md)**: de la tarjeta SD a encender tu PC desde el móvil, con scripts para cada paso.

## Requisitos

- Raspberry Pi con Raspberry Pi OS / Debian 13 y SSH habilitado.
- En el PC de desarrollo: Git Bash (o cualquier shell POSIX) con `ssh`, `scp` y `tar`.
- La Raspberry se indica una vez como `usuario@ip` (`scripts/install-all.sh` la guarda en `.pi-host`) o con la variable `PI_HOST`. `LAN_CIDR` (la red desde la que se permite SSH) se deduce de su IP; se puede forzar con la variable.

## Puesta en marcha (una sola vez)

Todo desde la carpeta del proyecto, en el PC:

```bash
bash scripts/install-all.sh      # acceso + aprovisionamiento + servicio + configuración + comprobación
```

O paso a paso (todos son idempotentes):

| Paso | Script | Qué hace |
|---|---|---|
| 1 | `bash scripts/setup-access.sh` | Llave SSH y `sudo` sin contraseña (pide la contraseña de la Raspberry una vez) |
| 2 | `bash scripts/provision.sh` | Caddy, `ufw` (solo 80/443 y SSH desde la LAN), SSH solo con llave, WiFi sin ahorro de energía, actualizaciones automáticas |
| 3 | `bash scripts/deploy.sh pc-power` | Instala el servicio (la primera vez espera su configuración) |
| 4 | `bash scripts/configure.sh` | Código de acceso, IP del PC, polaridad del relé, avisos |
| 5 | `bash scripts/check.sh` | Diagnóstico completo, de solo lectura |

Además: `scripts/backup.sh` y `scripts/restore.sh` (copia de la configuración), `scripts/remove.sh` (retirar un servicio).

Tras esto `https://<ip>/` responde 404 vacío (es lo esperado) y `https://<ip>/pc/` muestra la web. El certificado es autofirmado, así que el navegador avisará.

## Añadir un servicio

1. Reserva un puerto libre en `platform/PORTS.md` (fila nueva: puerto, `` `nombre` ``, prefijo).
2. Crea `services/<nombre>/` con tu aplicación. Debe escuchar en `127.0.0.1:$PORT` y usar **solo URLs relativas** (el prefijo `/<nombre>/` se recorta antes de llegar al servicio). Las cookies deben llevar `Path=/<nombre>/`.
3. Copia las plantillas a `services/<nombre>/deploy/`: `platform/templates/{service.unit,route.caddy,env.example}`. Los marcadores `@NAME@` y `@PORT@` se sustituyen al desplegar. Ajusta `ExecStart` en `service.unit` a tu aplicación.
   - Opcional: `deploy/install.sh` (ejecutable; instala dependencias, p. ej. un venv) y `deploy/groups` (grupos extra del usuario del servicio, uno por línea, p. ej. `gpio`).
4. Despliega: `bash scripts/deploy.sh <nombre>`. Termina mostrando `raspberryon-<nombre>: active`.
5. Prueba: `curl -k https://192.168.10.239/<nombre>/`.

Dónde queda cada cosa en la Raspberry:

| Qué | Dónde |
|---|---|
| Código | `/opt/raspberryon/<nombre>/` |
| Configuración y secretos | `/etc/raspberryon/<nombre>.env` (0640; **no se sobrescribe** al redesplegar) |
| Estado persistente | `/var/lib/raspberryon/<nombre>/` |
| Ruta en Caddy | `/etc/caddy/conf.d/<nombre>.caddy` |
| Logs | `journalctl -u raspberryon-<nombre>` |

Retirar un servicio: `bash scripts/remove.sh <nombre>` (borra unidad, ruta, usuario, código, `.env` y estado).

`services/hello/` es un ejemplo mínimo: `bash scripts/deploy.sh hello`.

## Dominio y certificado válido (Let's Encrypt)

Por defecto Caddy sirve `:443` con certificado autofirmado (cifra, pero el navegador avisa). Para un certificado válido:

1. Consigue un dominio que apunte a tu IP pública (DuckDNS es gratuito; si la IP cambia, usa DDNS en el enrutador).
2. En el enrutador, NAT del **443 externo → 443 de la Raspberry** (y opcionalmente 80 → 80). Con otro puerto externo Let's Encrypt no puede validar.
3. En la Raspberry:
   ```bash
   echo 'SITE_ADDRESS=mi-dominio.duckdns.org' | sudo tee /etc/caddy/site.env
   sudo truncate -s 0 /etc/caddy/tls.caddy      # sin "tls internal"
   sudo systemctl restart caddy
   ```
   `bootstrap.sh` no pisa `site.env` ni `tls.caddy` si ya existen.

Para volver al modo autofirmado: `#SITE_ADDRESS=` en `site.env` y restaurar `tls.caddy` con `tls internal { on_demand }`.

## Exponer a Internet (NAT)

Redirige en el enrutador el puerto externo elegido al **443** (o 80) de la IP de la Raspberry y reserva esa IP por DHCP. Ten en cuenta: SSH queda limitado a la LAN por el cortafuegos, y las rutas desconocidas devuelven 404 vacío sin revelar qué servicios existen.

## Reversión

En la Raspberry: `sudo ufw disable`, `sudo apt purge caddy`, `sudo rm -rf /opt/raspberryon /etc/raspberryon /etc/ssh/sshd_config.d/10-raspberryon.conf`, y `sudo systemctl reload ssh` para volver a permitir contraseña (hay copia del original en `/etc/ssh/sshd_config.bak`).

## Notas

- La Raspberry usa WiFi: reserva su IP en el enrutador y, si puedes, usa cable.
- Si compartiste la contraseña de la cuenta en algún chat, cámbiala con `passwd`.
