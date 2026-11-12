# pc-power

Sitio web para el móvil que enciende, apaga y fuerza el apagado de un PC cerrando un relé conectado al pulsador de encendido, desde una Raspberry Pi. Se publica bajo `/pc/` en la plataforma de este repositorio (ver el README de la raíz).

- Acceso protegido por un código compartido; cada navegador autorizado se recuerda 30 días.
- Un código erróneo no muestra ningún error: la respuesta es idéntica y genérica ("Solicitud recibida."). Tras 5 fallos por IP en 15 min (o 30 en total en 1 h) se bloquea en silencio, incluso con el código correcto.
- Estado del PC por ping: **Encendido** tras 1 respuesta, **Apagado** tras 3 pings seguidos sin respuesta.
- Acciones según estado: Apagado → **Encender**; Encendido → **Apagar** (pulso corto) y **Forzar apagado** (pulso largo, hay que mantener pulsado 2 s).

## Variables de entorno

Se definen en `/etc/raspberryon/pc-power.env` (en la Raspberry). El servicio **no arranca** si falta o es inválida alguna de las obligatorias.

| Variable | Defecto | Notas |
|---|---|---|
| `ACCESS_CODE` | obligatoria | Mínimo 8 caracteres; se recomiendan 12 o más |
| `PC_HOST` | obligatoria | IP local del PC (mejor con reserva DHCP) |
| `RELAY_ACTIVE_HIGH` | obligatoria | `true` o `false`; sin defecto a propósito (ver *Polaridad*) |
| `PC_NAME` | `PC` | Etiqueta en el panel |
| `RELAY_GPIO` | `23` | Numeración BCM |
| `SHORT_PULSE_MS` / `LONG_PULSE_MS` | `500` / `6000` | Corto < 2000; largo ≤ 10000 |
| `PING_INTERVAL_S` | `3` | |
| `TRANSITION_TIMEOUT_S` | `120` | Tras este tiempo sin cambio, avisa de que la acción no surtió efecto |
| `SESSION_DAYS` | `30` | |
| `COOKIE_PATH` | `/pc/` | Debe coincidir con el prefijo de Caddy |
| `COOKIE_SECURE` | `true` | `false` solo para desarrollo local por HTTP |
| `RELAY_DRIVER` | `gpio` | `mock` para desarrollo y pruebas (no toca el GPIO) |
| `TZ` | `America/Bogota` | Zona horaria de las programaciones y los recordatorios |
| `OFF_FORCE_AFTER_MIN` | `10` | Espera del apagado programado antes de forzarlo (0–120) |
| `APP_NAME` | `Panel` | Nombre neutro al instalar la app en el móvil |
| `PUBLIC_URL` | vacío | Dirección pública (solo esquema y host) para los botones del recordatorio |
| `REMINDER_AFTER_H` | `4` | Horas encendido antes del primer recordatorio |
| `REMINDER_TIMES` | `21:00,06:00` | Horas fijas (HH:MM, en `TZ`) de los recordatorios siguientes |
| `NTFY_URL` | vacío | Avisos push; ver *Notificaciones push* |
| `NTFY_TOKEN` | vacío | Token de acceso del tema ntfy (opcional) |
| `PORT` | `8101` | Solo escucha en `127.0.0.1` |

## Cableado del relé

> Trabaja con la Raspberry apagada. El relé solo se conecta al **pulsador de encendido** del PC (un contacto de baja tensión, no a la red eléctrica).

| Módulo de relé | Raspberry Pi |
|---|---|
| VCC | 5 V (pin físico 2 o 4) |
| GND | GND (pin físico 6) |
| IN | GPIO23 (pin físico 16) |

Los contactos **COM** y **NO** (normalmente abierto) del relé van **en paralelo con el pulsador** de la caja, a los dos pines `PWR_SW` / `POWER SW` de la placa base. No uses el contacto NC.

## Polaridad del relé

Hay módulos activos en alto (el relé cierra con el pin en alto) y activos en bajo (cierra con el pin en bajo). Con la polaridad equivocada el relé quedaría **cerrado en reposo**, lo que equivale a mantener pulsado el botón de encendido. Por eso `RELAY_ACTIVE_HIGH` es obligatoria y hay que determinarla **con el relé desconectado del PC**:

```bash
pinctrl set 23 op dh     # pin en alto: ¿cierra el relé (clic / LED)?
pinctrl set 23 op dl     # pin en bajo
pinctrl set 23 ip        # volver a entrada
```

- Si el relé hace clic con `dl` → es **activo en bajo** (`RELAY_ACTIVE_HIGH=false`) y el nivel de reposo es alto (`dh`).
- Si hace clic con `dh` → es **activo en alto** (`RELAY_ACTIVE_HIGH=true`) y el reposo es bajo (`dl`).

**En esta instalación**: el módulo es **activo en bajo** (`pinctrl set 23 op dl` cierra el relé y `op dh` / `ip` lo abren), por lo que se usa `RELAY_ACTIVE_HIGH=false` y `/boot/firmware/config.txt` lleva `gpio=23=op,dh`.

Para que el relé no se cierre mientras arranca la Raspberry, fija el nivel de reposo desde el firmware añadiendo a `/boot/firmware/config.txt` la línea `gpio=23=op,dh` (o `op,dl`) y reiniciando.

## Requisito en el PC controlado

El estado se detecta por ping, así que el PC **debe responder a ICMP** cuando está encendido. En Windows el firewall lo bloquea por defecto: habilita la regla *Archivos e impresoras compartidos (petición eco: ICMPv4 de entrada)*. Si no, el panel mostrará "Apagado" con el PC encendido y **Encender** lo apagaría. Reserva además su IP en el enrutador.

## Programar encendido y apagado

El panel permite dejar **un** encendido (con el PC apagado) y **un** apagado (con el PC encendido) a una hora de las próximas 24 h. Ambos conviven, se pueden cancelar y sobreviven a un reinicio del servicio o de la Raspberry.

- **Encendido**: a la hora fijada envía un pulso corto, solo si el PC sigue apagado.
- **Apagado**: a la hora fijada envía el apagado normal (pulso corto) y espera hasta `OFF_FORCE_AFTER_MIN` minutos (10 por defecto; Windows puede tardar por las actualizaciones). Si pasado ese plazo el PC sigue encendido, fuerza el apagado (pulso largo). **No fuerza nunca** si en ese intervalo el PC llegó a apagarse (aunque luego se vuelva a encender) ni si actúas tú desde el panel. Con las notificaciones activas llega un único aviso con el resultado: apagado normal, forzado o el PC sigue encendido.
- Una programación cuya hora pasó hace más de 5 minutos mientras el servicio estaba parado se descarta sin accionar el relé.

**Zona horaria**: las horas se interpretan y muestran en `TZ` (por defecto `America/Bogota`), independientemente de la zona del sistema. La Raspberry no tiene reloj propio: depende de NTP, así que tras un corte de luz sin Internet la hora puede ser incorrecta hasta que se sincronice. El panel muestra "Hora del equipo" junto a las programaciones para detectarlo. Comprobación: `timedatectl` debe decir `System clock synchronized: yes`.

## Recordatorio de apagado

Requiere las notificaciones push (`NTFY_URL`). Si el PC lleva **4 horas** (`REMINDER_AFTER_H`) encendido sin interrupción, llega un aviso preguntando si quieres apagarlo. Mientras siga encendido, el aviso se repite **indefinidamente a las 21:00 y a las 06:00** (`REMINDER_TIMES`, en `TZ`), salvo que ya se haya enviado otro hace menos de 30 minutos. Al apagarse el PC cesan los avisos, y al volver a encenderse el contador empieza de cero (si reinicias la Raspberry con el PC encendido, también).

El aviso lleva dos botones, que funcionan **sin abrir el panel ni escribir el código**:

- **Apagar**: apagado normal (pulso corto), solo si el PC sigue encendido.
- **Mantener encendido**: descarta ese aviso (el botón Apagar de ese aviso deja de valer); los avisos de las 21:00 y las 06:00 continúan.

Cómo funcionan y qué conviene saber:

- Los botones solo existen si defines `PUBLIC_URL` (p. ej. `https://mi-dominio.duckdns.org`, **solo esquema y host**): la app ntfy hace la petición desde tu móvil, así que la Raspberry debe ser alcanzable desde Internet en esa dirección. Sin `PUBLIC_URL` el aviso llega solo con el texto.
- **Necesitan un certificado válido.** La app ntfy rechaza el certificado autofirmado: configura un dominio con Let's Encrypt (README de la raíz) antes de esperar que el botón funcione.
- Cada aviso lleva un enlace propio, secreto y de **un solo uso** (`/pc/r/<token>/off` o `/keep`), que caduca con el siguiente aviso o a las 12 h. Solo permite el apagado normal o el descarte: nunca el apagado forzado, el encendido ni el acceso al panel. Un enlace usado, caducado o inventado da un 404 idéntico y no hace nada. Cada uso queda en el historial.
- **Riesgo**: quien pueda leer el tema de ntfy puede ver el enlace y apagar el PC una vez. Por eso se recomienda un tema con control de acceso (`NTFY_TOKEN`) o un servidor ntfy propio; en el ntfy público, el tema debe ser largo y aleatorio.

## Notificaciones push (opcional)

Avisan al móvil cuando se acepta una acción, una acción no surte efecto, se autoriza un navegador nuevo o hay un bloqueo por intentos fallidos. Se usa [ntfy](https://ntfy.sh): un simple `POST` sin cuentas ni SDK.

1. Instala la app **ntfy** en el móvil (Android / iOS) y suscríbete a un tema con un nombre largo y aleatorio, p. ej. `pc-7f3k9x2q8m4v1n6c0b5d`.
2. En `/etc/raspberryon/pc-power.env` añade `NTFY_URL=https://ntfy.sh/<tu-tema>` y reinicia el servicio.
3. Si usas un tema protegido o un servidor ntfy propio, añade `NTFY_TOKEN=<token de acceso>`.

Detalles: máximo 20 avisos por hora (el exceso se descarta); los avisos nunca llevan el código de acceso ni credenciales; si ntfy no responde, el control sigue funcionando y el fallo queda en `journalctl -u raspberryon-pc-power`. En el ntfy público **quien conozca el nombre del tema puede leer los avisos**, por eso conviene un nombre aleatorio o un tema con token.

## Cambiar el código de acceso

Edita `ACCESS_CODE` en `/etc/raspberryon/pc-power.env` y reinicia: `sudo systemctl restart raspberryon-pc-power`. Todas las sesiones existentes quedan invalidadas. También puedes usar "Cerrar todas las sesiones" en el panel.

## Despliegue

Desde la raíz del repositorio (ver el README principal): `bash scripts/deploy.sh pc-power`. En el primer despliegue el servicio falla a propósito hasta que rellenes `ACCESS_CODE`, `PC_HOST` y `RELAY_ACTIVE_HIGH`; después, `sudo systemctl restart raspberryon-pc-power`. Registros: `journalctl -u raspberryon-pc-power`.

## Desarrollo local (sin Raspberry)

Desde `services/pc-power`, en Git Bash (Windows):

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements-dev.txt
MSYS_NO_PATHCONV=1 ACCESS_CODE=codigo-de-prueba-1 PC_HOST=192.168.10.1 RELAY_ACTIVE_HIGH=false \
  RELAY_DRIVER=mock COOKIE_SECURE=false COOKIE_PATH=/ STATE_DIR=./data-dev \
  .venv/Scripts/python -m app
```

Abre `http://127.0.0.1:8101/`. En Linux/macOS usa `.venv/bin/python`. (`MSYS_NO_PATHCONV=1` evita que Git Bash convierta `COOKIE_PATH=/` en una ruta de Windows.) El relé simulado no toca ningún hardware.

Pruebas: `.venv/Scripts/python -m pytest -q`.
