# Proposal

## Why

La Raspberry Pi 3B+ (192.168.10.239, Raspberry Pi OS Lite recién instalado) va a alojar el control de encendido del PC y, más adelante, otros servicios, y quedará expuesta a Internet mediante una redirección NAT del enrutador. Antes de montar el primer servicio hace falta una base común: un único punto de entrada HTTPS, una convención para añadir servicios sin que se pisen entre sí y un endurecimiento mínimo del equipo.

## What Changes

- Un proxy inverso (Caddy) como único punto de entrada web: termina TLS, redirige HTTP→HTTPS y enruta cada servicio por prefijo de ruta (`/pc/`, `/otro/`…).
- Una convención de servicio: cada servicio vive en `services/<nombre>/` del repo, corre como unidad systemd con usuario propio, escucha solo en `127.0.0.1:<puerto>` y lee su configuración de un archivo de entorno fuera del repo.
- Un script de aprovisionamiento idempotente (`platform/bootstrap.sh`) y uno de despliegue (`scripts/deploy.sh <servicio>`) que se ejecutan desde el PC de desarrollo por SSH.
- Endurecimiento del host: cortafuegos (solo 80/443 públicos, SSH solo desde la LAN), SSH solo con llave, actualizaciones de seguridad automáticas.
- Las rutas desconocidas responden 404 vacío, sin revelar qué servicios existen.
- Modo TLS configurable: certificado autofirmado por defecto; Let's Encrypt automático cuando se configure un dominio.

## Capabilities

### New Capabilities
- `service-hosting`: punto de entrada HTTPS único, enrutamiento por prefijo, convención de aislamiento y configuración de servicios, y despliegue repetible.
- `host-security`: superficie de red expuesta, acceso administrativo por SSH y actualizaciones de seguridad del host.

### Modified Capabilities

Ninguna (proyecto nuevo, sin specs previas).

## Impact

- **Repo**: nuevos `platform/` (Caddyfile, bootstrap, plantillas de unidad systemd y de fragmento Caddy, registro de puertos), `scripts/deploy.sh`, `README.md`.
- **Raspberry Pi**: se instalan `caddy`, `ufw`, `unattended-upgrades`; se crean `/opt/raspberryon/`, `/etc/raspberryon/`, `/etc/caddy/conf.d/`; se modifica `sshd_config`.
- **Enrutador**: el NAT deberá apuntar al puerto 443 de la Raspberry (y opcionalmente al 80).
- **Dependencia para**: `add-pc-power-control` se despliega sobre esta plataforma.
- **Estado observado del host** (inspección de solo lectura): Debian 13 "trixie" arm64, Python 3.13, 905 MB de RAM, conectado por WiFi (`wlan0`), solo SSH escuchando, SSH con contraseña y `sudo` que pide contraseña.
