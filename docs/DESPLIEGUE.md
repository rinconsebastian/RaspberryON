# Guía de despliegue desde cero

Cómo montar RaspberryON en una Raspberry Pi nueva **sin ayuda**: de la tarjeta SD en blanco a encender y apagar tu PC desde el móvil. Tiempo estimado: 30–45 minutos la primera vez.

## Resumen rápido

1. Prepara la tarjeta SD con *Raspberry Pi Imager* (sección 3) y arranca la Raspberry (4).
2. Cablea el relé **sin conectarlo todavía al PC** (6) y averigua su polaridad (7).
3. Desde tu PC, en la carpeta del proyecto: `bash scripts/install-all.sh` (8).
4. Conecta el relé al pulsador de encendido y haz la primera prueba (9).
5. Opcional: acceso desde Internet (10) y avisos al móvil (11). **Antes, lee la sección 12.**

Para saber en cualquier momento si todo está bien: `bash scripts/check.sh`.

---

## 1. Qué vas a construir

```
 Tu móvil ──HTTPS──► Raspberry Pi ──relé──► pulsador de encendido del PC
                      │  Caddy (HTTPS, puerto 443)
                      │  pc-power (la web, solo en 127.0.0.1)
                      └─ ping ──► PC (para saber si está encendido)
```

- La web pide un **código de acceso** y recuerda cada navegador 30 días.
- Sabe si el PC está encendido haciéndole **ping**.
- Ofrece **Encender**, **Apagar** (pulso corto) y **Forzar apagado** (pulso largo, mantener pulsado 2 s).
- Extras: historial, programar un encendido y un apagado, recordatorio si el PC lleva horas encendido, avisos al móvil (ntfy) y panel instalable como app.

## 2. Materiales

| Qué | Notas |
|---|---|
| Raspberry Pi 3B+ (o 4) | Probado en la **3B+** con Raspberry Pi OS Lite (Debian 13, 64 bits). La **Pi 5** no vale tal cual (usa otro controlador de GPIO). |
| Tarjeta microSD de 16 GB o más, y fuente de 5 V / 2,5 A o más | Una fuente floja causa reinicios raros (`check.sh` avisa de subvoltaje). |
| Módulo de relé de **1 canal, 5 V** | El tipo habitual con optoacoplador y 3 pines de control (VCC, GND, IN) y 3 de contacto (COM, NO, NC). |
| 3 cables dupont hembra-hembra | VCC, GND, IN. |
| 2 cables para el pulsador | Hacia los pines `PWR_SW` de la placa base del PC. |
| Un PC con Git Bash (Windows) o una terminal (Linux/macOS) | Con `ssh`, `scp` y `tar`. En Windows: *Git for Windows*. |
| Cable de red (recomendado) | El WiFi funciona, pero un cable evita cortes. |

## 3. Preparar la tarjeta SD

1. Instala **Raspberry Pi Imager** en tu PC y elige: *Raspberry Pi OS Lite (64-bit)* (basado en Debian 13 "trixie").
2. Antes de grabar, pulsa **Editar ajustes** (el engranaje) y rellena:
   - **Nombre del equipo**: p. ej. `raspberryon`.
   - **Usuario y contraseña**: anótalos. El usuario será tu `usuario` en `usuario@ip`.
   - **WiFi** (si no usas cable): red y contraseña, y tu país.
   - **Zona horaria** y teclado.
   - **Servicios → Activar SSH** con autenticación por contraseña (el script instala luego tu llave).
3. Graba la tarjeta, ponla en la Raspberry y conéctala a la corriente.

## 4. Primer arranque y red

1. Espera 1–2 minutos y busca la IP de la Raspberry en la lista de dispositivos de **tu router** (o prueba `ping raspberryon.local`).
2. **Reserva esa IP** en el router (reserva DHCP): la IP no debe cambiar nunca. Haz lo mismo con la IP del **PC** que vas a controlar.
3. Comprueba que entras: `ssh usuario@IP` (acepta la huella, escribe la contraseña) y sal con `exit`.

## 5. Preparar tu PC

- Descarga o clona este proyecto en tu PC y abre **Git Bash** en su carpeta (en Windows: clic derecho → *Git Bash Here*).
- Comprueba que existen `ssh`, `scp` y `tar`: `ssh -V && tar --version`.
- Todos los comandos de esta guía se escriben **desde esa carpeta**, en el PC (no en la Raspberry), salvo que se diga lo contrario.

## 6. Cablear el relé

> Con la Raspberry **apagada**. El relé se conecta al pulsador de encendido del PC (un contacto de baja tensión). **Nunca a la red eléctrica.**
> En este paso conecta solo los 3 cables hacia la Raspberry; los contactos del relé quedan **sin conectar al PC** hasta la sección 9.

| Módulo de relé | Raspberry Pi |
|---|---|
| `VCC` | 5 V (pin físico 2 o 4) |
| `GND` | GND (pin físico 6) |
| `IN` | **GPIO23** (pin físico 16) |

Los contactos que usarás después son **COM** y **NO** (normalmente abierto). No uses NC.

## 7. Probar el relé y averiguar su polaridad (relé SIN conectar al PC)

Hay módulos "activos en bajo" (cierran cuando el pin está en bajo; lo habitual) y "activos en alto". Hay que saber cuál tienes. Enciende la Raspberry, entra por SSH (`ssh usuario@IP`) y ejecuta:

```bash
pinctrl get 23          # en reposo debe decir "ip" (entrada)
pinctrl set 23 op dl    # pin en BAJO: ¿hace "clic" el relé y se enciende su LED?
pinctrl set 23 ip       # ← SIEMPRE termina soltando el pin (el relé se abre)
```

- **Si `op dl` hace clic** → tu módulo es **activo en BAJO**. En la configuración responderás la opción 1.
- **Si no hace nada**, prueba el contrario:
  ```bash
  pinctrl set 23 op dh    # pin en ALTO
  pinctrl set 23 op dl    # vuelve a bajo (reposo de un módulo activo en alto)
  ```
  Si `op dh` hace clic → módulo **activo en ALTO** (opción 2).
- **Si con `dl` y con `dh` el relé queda cerrado** y solo se abre con `ip`: es un módulo de 5 V activo en bajo que no se suelta con 3,3 V. Es **activo en BAJO** y es el caso que el sistema maneja bien (no manda nunca un nivel alto: suelta el pin).

**Importante:** un pin que se deja como salida baja mantiene el relé cerrado, aunque cierres la sesión. Termina siempre con `pinctrl set 23 ip` (o `op dl` si es activo en alto). Si dudas, reinicia la Raspberry: arranca con el relé abierto.

## 8. Instalar

```bash
bash scripts/install-all.sh
```

La primera vez te pregunta la dirección `usuario@ip` de la Raspberry y la guarda en `.pi-host` (no se versiona). Después, paso a paso:

| Paso | Qué hace | Qué te pide |
|---|---|---|
| `access` | Crea tu llave SSH, la instala en la Raspberry y activa `sudo` sin contraseña | La contraseña de la Raspberry (y la de `sudo`), una vez cada una |
| `provision` | Instala Caddy, cortafuegos (solo 80/443 y SSH desde la red de tu PC; si tu PC y la Raspberry están en redes distintas, `LAN_CIDR=192.168.X.0/24 bash scripts/provision.sh`), SSH solo con llave, WiFi sin ahorro de energía, actualizaciones de seguridad automáticas | Nada |
| `deploy` | Instala el servicio `pc-power` | Nada. La primera vez avisa de que espera su configuración: es normal |
| `configure` | Código de acceso, IP del PC, polaridad, avisos | Ver abajo |
| `check` | Comprueba todo | Nada |

En **configure** responde:
- **IP del PC** que vas a controlar (la que reservaste en el router).
- **Polaridad**: la que averiguaste en la sección 7.
- **Código de acceso**: 12 o más caracteres, con letras. Se pide dos veces y no se muestra.
- **NTFY_URL** y **PUBLIC_URL**: déjalos en blanco; se ponen en las secciones 10 y 11.

Al terminar, abre `https://IP-de-la-Raspberry/pc/` en el móvil: el navegador avisa de que el certificado no es de confianza (es el autofirmado); acéptalo. Escribe tu código.

Puedes ejecutar solo algunos pasos (`bash scripts/install-all.sh configure check`) o cada script por separado. Todos son **idempotentes**: repetirlos no rompe nada.

## 9. Conectar el relé al PC y primera prueba

1. Apaga el PC y desconéctalo de la corriente (o apaga el interruptor de la fuente).
2. Localiza en la placa base los dos pines **`PWR_SW`** (a veces `POWER SW`), donde se conecta el pulsador de la caja. Mira el manual de la placa.
3. Conecta **COM** y **NO** del relé a esos dos pines, **en paralelo con el pulsador de la caja** (el botón sigue funcionando). La polaridad no importa: es un contacto seco.
4. Enciende la fuente y prueba **Encender** desde la web; después **Apagar**. El estado cambia a "Encendiendo…/Encendido" y "Apagando…/Apagado".

Requisitos en el PC controlado:
- **Debe responder a ping encendido.** En Windows el firewall lo bloquea por defecto: activa la regla *Archivos e impresoras compartidos (petición eco: ICMPv4 de entrada)*. Si no, la web mostrará "Apagado" con el PC encendido y **Encender** lo apagaría.
- **IP fija o reserva DHCP.**
- **Qué hace el botón de encendido al pulsarlo**: en Windows, *Opciones de energía → Elegir el comportamiento de los botones de inicio/apagado → Apagar*. Si hace "Suspender", **Apagar** suspenderá el equipo.

## 10. Acceso desde Internet (opcional)

Sin esto, la web solo se usa dentro de tu red. Cuando lo abras, **lee antes la sección 12**.

### Opción A: reenvío de puertos directo a la Raspberry
En el router, reenvía un puerto externo al **443** de la Raspberry. Con un dominio propio (p. ej. DuckDNS) y los puertos **80 y 443** externos llegando a la Raspberry, Caddy obtiene solo un certificado válido de Let's Encrypt:

```bash
ssh usuario@IP
echo 'SITE_ADDRESS=mi-dominio.duckdns.org' | sudo tee /etc/caddy/site.env
sudo truncate -s 0 /etc/caddy/tls.caddy      # quita "tls internal"
sudo systemctl restart caddy
```
Sin esos puertos libres, Let's Encrypt no puede validar y te quedas con el certificado autofirmado.

### Opción B: detrás de un proxy inverso (p. ej. un NAS Synology)
Si otro equipo ya ocupa los puertos 80/443 y mantiene el certificado de tu dominio, haz que sea la puerta de entrada:
- **Proxy inverso** (en DSM: *Panel de control → Portal de aplicaciones → Proxy inverso*): origen `HTTPS`, tu dominio y un puerto (p. ej. 2239); destino `HTTPS`, la IP de la Raspberry, puerto `443`.
- **Router**: reenvía ese puerto externo al **NAS**, no a la Raspberry.
- El certificado válido lo pone y renueva el NAS; la Raspberry mantiene el autofirmado.

**Limitación conocida:** con un proxy delante, el servicio ve todo el tráfico como venido de la IP del proxy. El límite de intentos fallidos (5 por IP) cuenta entonces a todo Internet como un solo cliente, y el historial muestra la IP del proxy. Está pendiente de resolver; hasta entonces, usa un código largo y no pongas un puerto conocido.

### Para los botones del aviso
Pon la dirección pública (solo esquema, host y puerto) y reinicia:
```bash
PUBLIC_URL=https://mi-dominio:puerto bash scripts/configure.sh
```
Los botones **necesitan un certificado válido**: la app ntfy rechaza el autofirmado.

## 11. Avisos al móvil (opcional)

Usan [ntfy](https://ntfy.sh): avisos de acciones, intentos de acceso, apagado programado y el **recordatorio** (si el PC lleva 4 h encendido, y después a las 21:00 y 06:00).

1. Instala la app **ntfy** en el móvil.
2. Inventa un tema **largo y aleatorio** (en ntfy.sh público el nombre del tema funciona como contraseña). Para generarlo:
   ```bash
   echo "pc-$(head -c 30 /dev/urandom | base64 | tr -dc 'a-z0-9' | head -c 22)"
   ```
3. En la app, suscríbete a ese tema.
4. Configúralo:
   ```bash
   NTFY_URL=https://ntfy.sh/TU-TEMA bash scripts/configure.sh
   ```
5. **Probar el recordatorio** (con el PC encendido): baja el umbral unos segundos y vuelve a dejarlo.
   ```bash
   ssh usuario@IP "echo REMINDER_AFTER_H=0.01 | sudo tee -a /etc/raspberryon/pc-power.env; sudo systemctl restart raspberryon-pc-power"
   # espera ~1 minuto: llega el aviso
   ssh usuario@IP "sudo sed -i '/^REMINDER_AFTER_H=/d' /etc/raspberryon/pc-power.env; sudo systemctl restart raspberryon-pc-power"
   ```

## 12. Antes de abrirlo a Internet (lista de seguridad)

- [ ] **Código de acceso de 12 o más caracteres con letras** (`bash scripts/configure.sh`). Es lo único que protege el botón.
- [ ] **Cambia la contraseña de la cuenta de la Raspberry** (`ssh usuario@IP` → `passwd`). Si la escribiste en algún chat o documento, cámbiala sí o sí.
- [ ] **Tema de ntfy largo y aleatorio** (o con token). Quien lo conozca lee tus avisos y los enlaces de Apagar.
- [ ] **HTTPS siempre.** El código y la cookie de sesión solo funcionan por HTTPS (la cookie es `Secure`).
- [ ] **No publiques el puerto SSH.** El cortafuegos ya lo limita a tu red local.
- [ ] Haz una **copia de seguridad** (sección 13).
- [ ] Haz una última pasada: `bash scripts/check.sh` sin ningún `XX`.

Lo que ya hace el sistema por ti: respuesta idéntica y genérica ante códigos erróneos, bloqueo silencioso tras 5 fallos por IP en 15 minutos, rutas desconocidas con 404 vacío, relé que se abre solo si el servicio falla o se reinicia, y un solo accionamiento a la vez.

## 13. Mantenimiento

| Quiero… | Comando |
|---|---|
| Ver si todo está bien | `bash scripts/check.sh` |
| Actualizar el servicio tras cambiar el código | `bash scripts/deploy.sh pc-power` |
| Cambiar el código de acceso, la IP del PC, avisos… | `bash scripts/configure.sh` (cambiar el código cierra todas las sesiones) |
| Ver el registro del servicio | `ssh usuario@IP "journalctl -u raspberryon-pc-power -n 50"` |
| Reiniciar el servicio (también quita un bloqueo por intentos) | `ssh usuario@IP "sudo systemctl restart raspberryon-pc-power"` |
| Copia de seguridad de la configuración | `bash scripts/backup.sh` (genera `backups/FECHA/`; **contiene el código en claro**) |
| Restaurar una copia | `bash scripts/restore.sh backups/FECHA` |

**Sustituir la Raspberry por otra:** `bash scripts/backup.sh` → prepara la SD nueva (secciones 3–4) → `bash scripts/install-all.sh access provision deploy` → `bash scripts/restore.sh backups/FECHA` → `bash scripts/check.sh`. Recuerda cablear el relé (sección 6) y actualizar el reenvío de puertos si cambió la IP.

El sistema se mantiene solo: instala las actualizaciones de seguridad automáticamente, el servicio arranca con la Raspberry y se reinicia si falla. Los certificados de Let's Encrypt (Caddy o tu NAS) se renuevan solos.

## 14. Problemas frecuentes

| Síntoma | Causa y solución |
|---|---|
| `Permission denied (publickey)` | La llave no está instalada o el SSH ya está limitado a llave: `bash scripts/setup-access.sh`. Si te quedaste fuera del todo: conecta teclado y pantalla, o edita la SD en tu PC, y borra `/etc/ssh/sshd_config.d/10-raspberryon.conf`. |
| `sudo` pide contraseña en los scripts | Falta el paso `access`: `bash scripts/setup-access.sh`. |
| **El relé se queda cerrado** (el botón del PC "pulsado") | Para el servicio y suelta el pin: `ssh usuario@IP "sudo systemctl stop raspberryon-pc-power; pinctrl set 23 ip"`. Revisa la polaridad (sección 7) y `bash scripts/configure.sh`. |
| La web dice "Apagado" con el PC encendido | El PC no responde a ping (firewall de Windows, sección 9) o la IP configurada es otra. |
| No puedo entrar: el código no funciona | Si lo escribiste mal 5 veces, estás bloqueado 15 minutos; reinicia el servicio para quitarlo. Comprueba que usas **HTTPS** (por HTTP la cookie no se guarda). |
| El navegador avisa del certificado | Es el autofirmado: normal en la red local. Para evitarlo, un dominio con certificado válido (sección 10). |
| Los botones del aviso no funcionan | Necesitan `PUBLIC_URL` y un **certificado válido** (sección 10), y que el puerto público llegue a la Raspberry. |
| `ERROR de configuración` en el registro | Falta o es inválido un dato: `bash scripts/configure.sh`. El servicio no arranca en bucle; al corregirlo se reinicia. |
| La hora de las programaciones está mal | Reloj sin sincronizar: `check.sh` lo avisa. Comprueba que la Raspberry tiene Internet. |
| La Raspberry se desconecta del WiFi | Usa cable y reserva su IP. El aprovisionamiento ya desactiva el ahorro de energía del WiFi. |
| Reinicios o `subvoltaje` en `check.sh` | Fuente o cable de poca potencia: usa 5 V / 2,5 A o más. |
| Los scripts fallan con `\r` o `$'\r': command not found` | Finales de línea de Windows: `sed -i 's/\r$//' scripts/*.sh platform/*.sh` (el proyecto ya fuerza LF con `.gitattributes`). |
| En Git Bash, una variable con `/` se convierte en una ruta de Windows | Antepón `MSYS_NO_PATHCONV=1` al comando. |
| `Puerto no registrado en platform/PORTS.md` | Al añadir un servicio nuevo, reserva su puerto en esa tabla. |

## 15. Desinstalar o volver atrás

- Quitar solo el servicio: `bash scripts/remove.sh pc-power`.
- Volver a permitir la contraseña de SSH: en la Raspberry, `sudo rm /etc/ssh/sshd_config.d/10-raspberryon.conf && sudo systemctl reload ssh`.
- Quitar el cortafuegos y Caddy: `sudo ufw disable && sudo apt purge caddy`.
- Desconecta el relé del PC antes de reinstalar o reformatear la tarjeta.

## 16. Referencia

**Scripts** (en el PC, desde la carpeta del proyecto):

| Script | Para qué |
|---|---|
| `install-all.sh [paso…]` | Todo el proceso: `access provision deploy configure check` |
| `setup-access.sh` | Llave SSH y `sudo` sin contraseña |
| `provision.sh` | Caddy, cortafuegos, SSH, WiFi, actualizaciones (idempotente) |
| `deploy.sh <servicio>` | Instala o actualiza un servicio (`pc-power`) |
| `configure.sh [--dry-run]` | Configura el servicio de forma guiada y lo reinicia |
| `check.sh` | Diagnóstico completo, solo lectura |
| `backup.sh` / `restore.sh` | Copia y restauración de la configuración |
| `remove.sh <servicio>` | Retira un servicio |

**En la Raspberry:**

| Qué | Dónde |
|---|---|
| Código del servicio | `/opt/raspberryon/pc-power/` |
| Configuración y secretos | `/etc/raspberryon/pc-power.env` (permisos 0640; el despliegue **no la sobrescribe**) |
| Estado (sesiones, historial, programaciones) | `/var/lib/raspberryon/pc-power/` |
| Caddy | `/etc/caddy/Caddyfile`, `/etc/caddy/site.env`, `/etc/caddy/tls.caddy`, `/etc/caddy/conf.d/` |
| Registro | `journalctl -u raspberryon-pc-power`, `journalctl -u caddy` |

**Todas las variables** de configuración y su valor por defecto: [services/pc-power/README.md](../services/pc-power/README.md). **Cómo añadir otro servicio** a la misma Raspberry: [README.md](../README.md).
