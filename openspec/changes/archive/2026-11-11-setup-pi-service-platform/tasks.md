# Tasks

## 1. Acceso y verificación del host

- [x] 1.1 Instalar la llave pública SSH del equipo de desarrollo en la Pi (`ssh-copy-id` o equivalente; el usuario introduce la contraseña una vez) y verificar que `ssh -o BatchMode=yes rinconsebastian@192.168.10.239 true` termina con código 0
- [x] 1.2 Escribir `platform/enable-sudo.sh` (instala `/etc/sudoers.d/010-raspberryon-admin` validado con `visudo -c`) y ejecutarlo una vez con `ssh -t` (el usuario teclea su contraseña); verificar que `ssh rinconsebastian@192.168.10.239 sudo -n true` termina con código 0
- [x] 1.3 Registrar en `platform/HOST.md` los datos del host (Debian 13 trixie arm64, Python 3.13, WiFi `wlan0`, IP) y verificar que coinciden con `cat /etc/os-release; uname -m; python3 --version; ip -4 -br addr`

## 2. Estructura del repo y plantillas

- [x] 2.1 Crear `platform/` con `Caddyfile` (global, redirección 80→443, `import conf.d/*.caddy`, 404 vacío por defecto, sin cabecera `Server`, modo TLS según `SITE_ADDRESS`) y verificar con `caddy validate` en la Pi
- [x] 2.2 Crear plantillas `platform/templates/{service.unit,route.caddy,env.example}` con el endurecimiento systemd de D1 y `platform/PORTS.md` (registro de puertos desde 8101); verificar que `systemd-analyze verify` acepta la plantilla con valores de ejemplo
- [x] 2.3 Añadir `.gitignore` (archivos `.env`, `__pycache__`, venv) y verificar que `git status` no muestra archivos de entorno

## 3. Aprovisionamiento

- [x] 3.1 Escribir `platform/bootstrap.sh` idempotente: instala `caddy`, `ufw`, `unattended-upgrades`; crea `/opt/raspberryon`, `/etc/raspberryon`, `/etc/caddy/conf.d`, `/etc/caddy/site.env`; limita journald; habilita servicios. Verificar ejecutándolo dos veces: la segunda termina con código 0 y sin cambios
- [x] 3.2 Configurar `ufw` en el bootstrap (deny incoming; 80, 443; 22 solo desde 192.168.10.0/24) y verificar con `sudo ufw status verbose` y con una conexión rechazada a un puerto no publicado desde el PC
- [x] 3.3 Endurecer SSH en el bootstrap (copia `sshd_config.bak`, `PasswordAuthentication no` solo si la sesión actual usa llave); verificar que `ssh -o PubkeyAuthentication=no` es rechazado y que la sesión por llave sigue funcionando
- [x] 3.4 Desactivar en el bootstrap el ahorro de energía de `wlan0` de forma persistente y verificar con `iw dev wlan0 get power_save` (Power save: off) tras un reinicio
- [x] 3.5 Activar `unattended-upgrades` y verificar con `systemctl is-enabled unattended-upgrades` y `unattended-upgrade --dry-run`

## 4. Punto de entrada

- [x] 4.1 Desplegar el Caddyfile y verificar desde el PC: `curl -I http://192.168.10.239/x` redirige a https; `curl -k -i https://192.168.10.239/` devuelve 404 con cuerpo vacío y sin cabecera `Server`
- [x] 4.2 Verificar que tras `sudo reboot` Caddy vuelve a responder sin intervención

## 5. Despliegue de servicios

- [x] 5.1 Escribir `scripts/deploy.sh <nombre>` (tar por ssh; usuario `svc-<nombre>`; código en `/opt/raspberryon/<nombre>`; `install.sh` opcional; `.env` solo si no existe, 0640; unidad + fragmento; restart + reload; imprime `is-active`). Verificar con un servicio de prueba `services/hello` (servidor HTTP mínimo en 127.0.0.1:8199): `curl -k https://192.168.10.239/hello/` responde y `curl http://192.168.10.239:8199` es rechazado
- [x] 5.2 Verificar idempotencia y conservación de secretos: editar el `.env` de `hello` en la Pi, redesplegar y comprobar que el `.env` no cambió; matar el proceso y comprobar que systemd lo reinicia en <10 s
- [x] 5.3 Retirar el servicio de prueba `hello` (script `scripts/remove.sh <nombre>`) y verificar que `/hello/` devuelve 404 y no quedan unidad, usuario ni fragmento

## 6. Documentación

- [x] 6.1 Escribir `README.md`: requisitos, bootstrap, cómo añadir un servicio (carpeta, puerto, prefijo, URLs relativas), cómo pasar a dominio + Let's Encrypt (`SITE_ADDRESS`, NAT 443→443, DDNS), y reversión; verificar siguiendo el apartado "añadir un servicio" tal como está escrito con el servicio `hello`
