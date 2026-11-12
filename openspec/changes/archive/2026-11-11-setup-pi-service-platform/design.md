# Design

## Context

Repo vacío (solo `openspec/`). Destino: Raspberry Pi 3B+ (1 GB RAM, 4 núcleos ARMv8) en `192.168.10.239`, usuario `rinconsebastian`, Raspberry Pi OS Lite recién instalado. El equipo de desarrollo es Windows 11 con Git Bash y OpenSSH. Se expondrá a Internet por NAT.

**Observado en el host** (inspección de solo lectura por SSH):
- Debian 13 "trixie", `aarch64`/arm64, Python 3.13.5, 905 MB de RAM (≈740 MB libres), 11 GB libres en la SD.
- Red por **WiFi** (`wlan0`, 192.168.10.239/24); solo el puerto 22 escucha.
- SSH acepta contraseña; aún no hay llave instalada.
- `sudo` **pide contraseña** (no hay NOPASSWD); el usuario pertenece a `sudo` y `gpio`.
- No están instalados `caddy`, `nginx`, `docker` ni `ufw`.

## Goals / Non-Goals

**Goals:**
- Añadir un servicio nuevo = una carpeta en `services/`, un puerto en el registro y un `deploy.sh <nombre>`.
- Consumo mínimo de RAM y cero mantenimiento manual de certificados.
- Que el host sea razonable de exponer por NAT.

**Non-Goals:**
- Contenedores, orquestación, CI/CD.
- Autenticación común entre servicios (cada servicio protege lo suyo).
- DNS dinámico, VPN o configuración del enrutador (se documentan, no se automatizan).
- Monitoreo/alertas del propio host.

## Decisions

### D1. Servicios nativos con systemd, no Docker
Cada servicio es una unidad `raspberryon-<nombre>.service` con usuario propio `svc-<nombre>`, `Restart=always`, `RestartSec=3` y endurecimiento (`NoNewPrivileges`, `ProtectSystem=strict`, `ProtectHome`, `PrivateTmp`, `StateDirectory=raspberryon/<nombre>`).
- *Por qué*: con 1 GB de RAM y tarjeta SD, Docker añade ~100 MB+ y escrituras; además el primer servicio necesita GPIO y ICMP, que en contenedor obligan a mapear dispositivos y capacidades. systemd ya da aislamiento, reinicio y logs (`journalctl`).
- *Alternativa*: Docker Compose — más portable, pero más pesado y sin ventaja real para 2–5 servicios pequeños. La convención (puerto local + fragmento Caddy) no impide que un servicio futuro sea un contenedor.

### D2. Caddy como proxy inverso
Paquete `caddy` de apt. `/etc/caddy/Caddyfile` contiene solo lo global e `import /etc/caddy/conf.d/*.caddy`; cada servicio aporta su fragmento.
- *Por qué*: HTTPS automático (CA interna o Let's Encrypt) con una línea, binario único, ~30 MB de RAM.
- *Alternativa*: nginx + certbot — más piezas y renovación aparte.

### D3. Enrutamiento por prefijo de ruta, con prefijo recortado
Fragmento tipo:
```
redir /pc /pc/ 308
handle_path /pc/* {
    reverse_proxy 127.0.0.1:8101
}
```
El servicio recibe las rutas sin prefijo y **debe usar solo URLs relativas** y cookies con `Path=/<prefijo>/`. Todo lo no capturado: `respond 404` vacío; se elimina la cabecera `Server`.
- *Por qué*: funciona con una sola IP/host y un solo certificado; los subdominios exigirían DNS comodín, imposible accediendo por IP.
- *Alternativa*: un puerto externo por servicio — más reglas NAT y más superficie.

### D4. TLS: autofirmado por defecto, Let's Encrypt al definir dominio
`/etc/caddy/site.env` define `SITE_ADDRESS`. Vacío → sitio `:443` con `tls internal` (on-demand, válido para cualquier IP/nombre). Con dominio → Caddy gestiona Let's Encrypt (reto TLS-ALPN por 443 o HTTP por 80).
- *Por qué*: el código de acceso viajará por Internet; sin TLS sería legible. El autofirmado cifra desde el día uno (con advertencia del navegador) y pasar a certificado válido es cambiar una variable.
- *Requisito para Let's Encrypt*: el NAT debe mapear el **443 externo → 443 de la Pi** (o el 80). Con un puerto externo arbitrario no hay validación posible sin reto DNS (requeriría compilar Caddy con plugin; fuera de alcance).

### D5. Distribución en disco
| Qué | Dónde |
|---|---|
| Código + venv del servicio | `/opt/raspberryon/<nombre>/` (root:root, solo lectura para el servicio) |
| Entorno/secretos | `/etc/raspberryon/<nombre>.env` (root:svc-<nombre>, 0640) |
| Estado persistente | `/var/lib/raspberryon/<nombre>/` (StateDirectory) |
| Fragmento Caddy | `/etc/caddy/conf.d/<nombre>.caddy` |
| Puertos internos | `127.0.0.1:8101+`, registrados en `platform/PORTS.md` |

En el repo, cada servicio aporta `services/<nombre>/deploy/{service.unit, route.caddy, env.example}` y opcionalmente `install.sh` (dependencias propias).

### D6. Despliegue por SSH con tar, sin rsync
`scripts/deploy.sh <nombre>` (Git Bash): empaqueta `services/<nombre>` con `tar`, lo envía por `ssh`, y en la Pi un paso con `sudo` crea el usuario, instala código, ejecuta `install.sh`, copia `env.example` solo si no existe el `.env`, instala unidad y fragmento, hace `systemctl restart` + `caddy reload` y muestra `systemctl is-active`.
- *Por qué*: Git Bash en Windows no trae `rsync`; `tar | ssh` no requiere nada extra.
- `platform/bootstrap.sh` se ejecuta igual (enviado por ssh) y es idempotente.

### D7. sudo sin contraseña para el usuario de administración
`platform/enable-sudo.sh` se ejecuta **una vez, de forma interactiva** (`ssh -t`, el usuario teclea su contraseña) e instala `/etc/sudoers.d/010-raspberryon-admin` con `rinconsebastian ALL=(ALL) NOPASSWD: ALL`, validado con `visudo -c`.
- *Por qué*: bootstrap y despliegue deben poder ejecutarse sin terminal interactiva (también por un agente). Es el comportamiento por defecto de Raspberry Pi OS y, con SSH solo por llave y solo desde la LAN, el riesgo añadido es bajo.
- *Alternativa*: `ssh -t` pidiendo contraseña en cada despliegue — más seguro pero no automatizable; o NOPASSWD limitado a un script instalador — más complejo de mantener.
- La contraseña de la cuenta no se guarda en el repo ni en scripts.

### D8. Cortafuegos y SSH
`ufw`: default deny incoming; allow 80, 443; allow 22 solo desde `192.168.10.0/24`. `sshd`: `PasswordAuthentication no` únicamente después de que el bootstrap confirme que existe una llave en `authorized_keys` y que la sesión actual usa llave. `unattended-upgrades` activado.

## Risks / Trade-offs

- [Quedar fuera por SSH al desactivar contraseñas] → el bootstrap comprueba la llave antes; hay acceso físico (teclado/HDMI o editar la SD) como último recurso.
- [Certificado autofirmado: advertencia del navegador y sin protección ante MITM activo] → documentado; recomendación: dominio (p. ej. DuckDNS gratuito) + NAT 443→443.
- [IP pública dinámica] → fuera de alcance; el README apunta a DDNS del enrutador o DuckDNS.
- [Raspberry por WiFi: microcortes dejan el panel inaccesible] → desactivar el ahorro de energía de `wlan0` en el bootstrap; recomendación documentada de reserva DHCP para la Pi y, si es posible, cable Ethernet.
- [La contraseña de la cuenta se compartió en texto y parece poco robusta] → tras instalar la llave queda inutilizable por SSH; se recomienda cambiarla con `passwd`.
- [Desgaste de la SD] → sin logs propios en disco; solo journald con límite de tamaño.

## Migration Plan

Instalación nueva. Reversión: `ufw disable`, `apt purge caddy`, borrar `/opt/raspberryon`, `/etc/raspberryon`; restaurar la copia `sshd_config.bak` que el bootstrap deja.

## Open Questions

- ¿Se usará dominio (DuckDNS u otro) y NAT 443→443? No bloquea: se arranca en autofirmado y se cambia `SITE_ADDRESS` después.
