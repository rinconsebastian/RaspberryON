# Design

## Context

Se despliega sobre la plataforma de `setup-pi-service-platform`: unidad systemd con usuario propio, escucha en `127.0.0.1:8101`, publicado por Caddy bajo `/pc/` con el prefijo recortado (el servicio usa solo URLs relativas), configuración en `/etc/raspberryon/pc-power.env`. Hardware: Pi 3B+, relé en GPIO23 (BCM) en paralelo al pulsador de encendido del PC. El sitio quedará accesible desde Internet.

Observado en el host (solo lectura): Debian 13 trixie arm64, Python 3.13.5, `gpiozero` y `lgpio` ya instalados e importables, `pinctrl` disponible, `/dev/gpiochip0` presente, grupo `gpio` existente. `pinctrl get 23` devuelve `ip -- | hi`: el pin está como entrada y **lee nivel alto**, lo que sugiere que el módulo de relé tiene pull-up en su entrada y es probablemente **activo en bajo**. Es un indicio, no una confirmación: la tarea 1.2 lo determina con el relé desconectado del PC.

## Goals / Non-Goals

**Goals:**
- Un solo proceso pequeño (<60 MB RAM), sin base de datos externa ni paso de compilación del frontend.
- Lógica (sesiones, límites, máquina de estados) probable en el PC de desarrollo sin hardware.
- Fallo seguro: ante cualquier duda, el relé queda abierto.

**Non-Goals:**
- Varios PCs o varios relés (la configuración es de un único PC).
- Usuarios/roles: hay un único código compartido.
- Wake-on-LAN, apagado por red o agente en el PC.
- Historial, notificaciones e instalación como app (ver `add-power-control-extras`).

## Decisions

### D1. Python + FastAPI + uvicorn, un único worker
`services/pc-power/app/` con módulos `config`, `auth`, `monitor`, `relay`, `power` (máquina de estados), `main` (rutas). Venv en `/opt/raspberryon/pc-power/venv` creado con `--system-site-packages` para reutilizar `python3-gpiozero`/`python3-lgpio` de apt.
- *Por qué*: Python y gpiozero son lo nativo en Raspberry Pi OS; asyncio encaja con el bucle de ping y los pulsos temporizados. **Un solo worker es obligatorio**: el cerrojo del relé y el estado viven en memoria del proceso.
- *Alternativas*: Flask + hilos (más enredo para temporizadores); Node (peor soporte GPIO actual); Go (binario ideal pero GPIO/iteración más lentos de desarrollar).

### D2. Relé con lgpio directo y salida en "colector abierto"
Driver propio sobre `lgpio` (sin gpiozero). `RELAY_ACTIVE_HIGH` es obligatoria (el servicio no arranca sin ella). El pulso es `on(); await sleep(d); off()` dentro de `try/finally`, con reserva síncrona del relé (`start()`) y cooldown de 5 s. **Al morir el proceso el núcleo solo libera la línea: el pin conserva su último estado**, así que un `kill -9` o un fallo durante un pulso dejaría el relé cerrado (comprobado en la Pi). Por eso `python -m app.release` deja el relé abierto y la unidad lo ejecuta en `ExecStartPre` y en `ExecStopPost` (que corre tras cualquier terminación, incluida una señal).
- **Módulo activo en bajo (el de esta instalación)**: cerrado = pin como salida en **bajo**; abierto = pin como **entrada sin sesgo** (alta impedancia). **No** se maneja nunca en alto: los módulos de 5 V con entrada activa en bajo no se sueltan de forma fiable con un 3,3 V manejado (comprobado: `op dl` y `op dh` los mantienen cerrados; solo `ip` los abre). La primera versión (gpiozero `OutputDevice`, reposo manejado en alto) cerró el relé al arrancar el servicio; de ahí este diseño.
- **Módulo activo en alto**: cerrado = salida en alto; abierto = salida en bajo.
- **Arranque de la Pi**: GPIO23 arranca como entrada, que es el estado abierto de este módulo; **no** se añade ninguna línea `gpio=` a `/boot/firmware/config.txt`.
- Usuario `svc-pc-power` en el grupo `gpio`; la unidad systemd permite `/dev/gpiochip0` (`DeviceAllow`).

### D3. Ping mediante el binario `ping` del sistema
`asyncio.create_subprocess_exec("ping", "-n", "-c", "1", "-W", "1", PC_HOST)` cada `PING_INTERVAL_S`. `PC_HOST` se valida con `ipaddress` al arrancar (nunca llega texto arbitrario al subproceso).
- *Por qué*: `ping` de iputils funciona sin root en Raspberry Pi OS y evita sockets raw o dependencias. El endurecimiento systemd no debe quitar `CAP_NET_RAW` ni activar `PrivateNetwork`; se verifica en tareas.
- *Alternativa*: `icmplib` sin privilegios — depende de `net.ipv4.ping_group_range`; innecesario.

### D4. Máquina de estados
`checking → off | on`; `off --pulso corto--> starting --ping ok--> on`; `on --pulso corto/largo--> stopping --3 fallos--> off`; `starting/stopping --timeout--> estado detectado + aviso "sin efecto"`. Encendido: 1 ping ok. Apagado: 3 fallos seguidos. Se guarda `since` (momento del último cambio).
Validación en servidor: `power_on` solo en `off`; `soft_off` solo en `on`; `force_off` en `on`, `off`, `stopping` (PC colgado o apagado que no termina). Nada en `checking`.

### D5. API (rutas relativas al prefijo)
| Ruta | Sin sesión | Con sesión |
|---|---|---|
| `GET ./` | formulario de código | panel |
| `POST ./login` | 303 → `./?s=1` (siempre) | igual |
| `GET ./api/status` | 404 | `{state, since, busy, notice}` |
| `POST ./api/action` `{type}` | 404 | 202 / 409 (ocupado o estado no válido) |
| `POST ./api/logout`, `./api/logout-all` | 404 | 204 |

El panel consulta `./api/status` cada 2 s mientras `document.visibilityState === "visible"`.
- *Por qué sondeo y no SSE/WebSocket*: un usuario, respuesta de ~100 bytes; sobrevive a redes móviles y proxys sin lógica de reconexión.

### D6. Respuesta indistinguible del login
`POST ./login` siempre: espera hasta completar un tiempo fijo (~800 ms desde la recepción), responde 303 a `./?s=1` con el mismo cuerpo. La única diferencia en acierto es la cabecera `Set-Cookie`. `GET ./?s=1` sin sesión pinta el formulario con "Solicitud recibida."; con sesión pinta el panel. Comparación con `hmac.compare_digest` sobre SHA-256 de ambos valores. El formulario no menciona "PC", "encender" ni el nombre del proyecto; título neutro.
- *Límite conocido*: un atacante que acierte ve el panel; "indistinguible" aplica a los fallos y al bloqueo, no al éxito.

### D7. Sesiones en servidor, persistidas en archivo
Token aleatorio de 256 bits en cookie `pcp_session` con `HttpOnly; Secure; SameSite=Strict; Path=/pc/; Max-Age=2592000`. En `/var/lib/raspberryon/pc-power/sessions.json` se guarda solo `sha256(token)`, expiración y la huella del código vigente (`sha256(ACCESS_CODE)` truncada). Escritura atómica (archivo temporal + rename). Al arrancar se descartan sesiones caducadas o con huella distinta → rotar el código cierra todo.
- *Por qué no cookie firmada sin estado*: no permitiría "cerrar todas las sesiones" ni revocar un navegador.
- *Por qué no SQLite*: son a lo sumo decenas de registros con escrituras muy esporádicas.
- La expiración es fija a 30 días desde la autorización (no deslizante), tal como se pidió.

### D8. Límite de intentos en memoria
Ventanas deslizantes: 5 fallos/15 min por IP, 30 fallos/1 h global. En bloqueo se devuelve la respuesta genérica sin evaluar el código. IP del cliente: primer valor de `X-Forwarded-For` **solo** si el par es `127.0.0.1` (Caddy). En memoria: un reinicio lo limpia, aceptable.
- *Trade-off*: el bloqueo global permite a un atacante dejar fuera temporalmente al dueño (solo para **nuevos** navegadores; los ya autorizados no se ven afectados). Con 30/h y código ≥ 8 caracteres la fuerza bruta es inviable.

### D9. CSRF y cabeceras
`SameSite=Strict` + comprobación de origen en todo POST: `Sec-Fetch-Site` manda si existe (debe ser `same-origin`; el navegador lo fija y no es falsificable desde la página) y, sin él, se compara `Origin` con `Host`; acciones solo por `fetch` con JSON. Cabeceras: `Content-Security-Policy: default-src 'self'`, `X-Frame-Options: DENY`, `Referrer-Policy: same-origin` (con `no-referrer` Chrome envía `Origin: null` en los formularios y rompía el login legítimo), `Cache-Control: no-store`, `X-Robots-Tag: noindex`.

### D10. Frontend estático sin build
`static/` con un HTML, un CSS y un JS sin dependencias. Estado grande arriba (color + texto), botón principal a todo el ancho, "Forzar apagado" con mantener-pulsado (barra de progreso de 2 s), opciones secundarias y cierres de sesión en un `<details>`. Tema claro/oscuro según el sistema.

### D11. Variables de entorno
| Variable | Defecto | Notas |
|---|---|---|
| `ACCESS_CODE` | — (obligatoria, ≥ 8) | |
| `PC_HOST` | — (obligatoria, IP) | |
| `PC_NAME` | `PC` | etiqueta en el panel |
| `RELAY_GPIO` | `23` | BCM |
| `RELAY_ACTIVE_HIGH` | — (obligatoria) | sin valor por defecto: una polaridad errónea mantendría el relé cerrado |
| `SHORT_PULSE_MS` / `LONG_PULSE_MS` | `500` / `6000` | máx. 10000; corto < 2000 |
| `PING_INTERVAL_S` | `3` | |
| `TRANSITION_TIMEOUT_S` | `120` | |
| `SESSION_DAYS` | `30` | |
| `PORT` | `8101` | |
| `RELAY_DRIVER` | `gpio` | `mock` para desarrollo/pruebas |

## Risks / Trade-offs

- [PC encendido que no responde a ping (firewall de Windows, suspensión)] → el panel ofrecería "Encender" y el pulso lo apagaría/suspendería. Mitigación: requisito documentado de permitir ICMP y tarea de verificación; reserva DHCP para el PC.
- [Polaridad del relé equivocada → relé cerrado permanentemente = apagado forzado] → primera tarea de hardware se hace con el relé **desconectado del PC**, midiendo/escuchando el clic.
- [Código débil expuesto a Internet] → mínimo 8 caracteres, límites de intentos, HTTPS de la plataforma. Se recomienda un código de 12+ caracteres.
- [Certificado autofirmado + `Secure` cookie] → funciona tras aceptar la advertencia; ver plataforma D4.
- [Pulso largo de 6 s insuficiente o excesivo en alguna placa] → configurable; ACPI estándar corta a los 4 s.
- [Corte de energía de la Pi a mitad de pulso] → al perder alimentación el relé se abre (normalmente abierto).

## Migration Plan

Servicio nuevo. Despliegue: `scripts/deploy.sh pc-power`, editar `/etc/raspberryon/pc-power.env`, reiniciar. Reversión: `scripts/remove.sh pc-power` y quitar la línea `gpio=23=…` de `config.txt`.

## Open Questions

- Polaridad real del módulo de relé: se resuelve en la tarea 1.2 y solo cambia un valor de configuración.
