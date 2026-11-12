# Design

## Context

Extiende el servicio `pc-power`, ya implementado y desplegado (`add-pc-power-control`, archivado): FastAPI en un único proceso, rutas en `app/main.py`, sesiones en `app/sessions.py`, limitador en `app/ratelimit.py`, máquina de estados en `app/power.py`, ping en `app/monitor.py`, relé en `app/relay.py` (reserva síncrona con `Relay.start()`, driver de colector abierto) y liberación del relé por systemd (`app/release.py`). Estado persistente en `/var/lib/raspberryon/pc-power/`, frontend estático sin build, publicado bajo `/pc/`.

## Goals / Non-Goals

**Goals:**
- Añadir las seis mejoras sin tocar el comportamiento especificado del control básico, salvo la excepción acotada de `access-gate` para los enlaces de recordatorio.
- Cada mejora desactivable o ignorable; ninguna puede impedir accionar el relé.
- Sin dependencias Python nuevas.

**Non-Goals:**
- Programaciones recurrentes de acciones (encender o apagar cada día). Lo único que se repite son los *avisos* del recordatorio.
- Apagado forzado o encendido desde la notificación.
- Web Push nativo, Telegram, correo.
- Funcionamiento sin conexión del panel.
- Exportar el historial.

## Decisions

### D1. Bus de eventos interno mínimo
Módulo `events.py`: `emit(tipo, **datos)` que reparte de forma síncrona a suscriptores registrados (historial, notificador, recordatorio, programador). Puntos de emisión: login correcto y cruce del umbral de bloqueo (`main.login`), acción aceptada y logout (`main`), cambio de estado y acción sin efecto (gancho nuevo en `PowerMachine._mark_change` / `_expire_transition`). Los suscriptores no pueden lanzar hacia el emisor (se capturan y registran).
- *Por qué*: un solo punto de enganche; el control básico no conoce a ninguno de los consumidores.

### D2. Historial en archivo JSON Lines con rotación
`events.jsonl`: una línea por evento `{ts, type, ip?, detail}`; se añade con `append`. Al superar 1200 líneas se reescribe con las últimas 1000 (archivo temporal + rename). En memoria, una `deque(maxlen=1000)` cargada al arrancar sirve `GET ./api/events?limit=50`.
- *Por qué no SQLite*: volumen mínimo, sin consultas complejas; menos escrituras en la SD.
- "Externo": un cambio de estado se marca externo si no hay acción del panel, programada ni de recordatorio en los `TRANSITION_TIMEOUT_S` anteriores.
- El bloqueo por IP emite un evento solo al cruzar el umbral, no en cada intento posterior.

### D3. Notificaciones con ntfy por HTTP
Variables: `NTFY_URL` (p. ej. `https://ntfy.sh/<tema-aleatorio-largo>`) y `NTFY_TOKEN` opcional. Envío con `urllib.request` en `asyncio.to_thread`, timeout 5 s, cola `asyncio.Queue(maxsize=50)` con una tarea consumidora; si la cola está llena o se supera 20/h, se descarta. Nunca se espera el envío desde la ruta de acción.
- *Por qué ntfy*: un POST sin SDK ni cuenta, app para Android/iOS con **botones de acción** (necesarios para D9), autoalojable en la misma Pi más adelante.
- *Alternativas*: Telegram (bot y chat_id; también tiene botones, pero más piezas); Web Push (VAPID, service worker, permisos en iOS solo con app instalada).
- *Privacidad*: en `ntfy.sh` público el nombre del tema actúa de contraseña. Con D9 eso pasa a ser más importante (ver Riesgos): se recomienda un tema con control de acceso (`NTFY_TOKEN`) o un servidor ntfy propio.

### D4. PWA mínima
`manifest.webmanifest` (nombre neutro configurable `APP_NAME`, por defecto "Panel"; `display: standalone`; `start_url: ./`; `scope: ./`), iconos 192/512 y `apple-touch-icon`, metaetiquetas de iOS. Service worker mínimo solo para cumplir el criterio de instalación de Chrome: **sin caché de API ni de HTML** (network-only), de modo que sin conexión el panel muestra su propio "Sin conexión".
- El manifiesto y los iconos se sirven sin sesión, por eso el nombre es neutro y el icono genérico.

### D5. Programador común (encendido y apagado únicos)
`schedule.json` con `{on: <ISO UTC>|null, off: <ISO UTC>|null, off_wait: {started, deadline}|null}`. Una tarea asyncio por programación pendiente que duerme hasta su hora. Al arrancar: cualquier hora vencida hace > 5 min se descarta y emite evento. API: `GET ./api/schedule`, `PUT/DELETE ./api/schedule/on`, `PUT/DELETE ./api/schedule/off`. El panel usa `<input type="time">`; el servidor convierte HH:MM a la próxima ocurrencia en `TZ` (por defecto `America/Bogota`, con `zoneinfo`).
- **Encendido**: al vencer, si el estado es `off` → misma ruta interna que "Encender" (`Relay.start` + `PowerMachine.on_action_started`); si el relé está ocupado reintenta una vez a los 10 s; si no está `off`, descarta.
- Eventos `schedule_set`, `schedule_fired`, `schedule_discarded`, `schedule_cancelled`, con `kind: on|off`.
- *Por qué no systemd timers/cron*: el estado y el cerrojo del relé viven en el proceso.
- Requiere reloj correcto: la Pi no tiene RTC; la regla de "vencida > 5 min" y NTP lo acotan.

### D7. Apagado programado con forzado de respaldo
Al vencer `off`: si el estado no es `on` → descarta. Si es `on` → pulso corto (`soft_off`) y se abre una **espera de forzado** de `OFF_FORCE_AFTER_MIN` (10 por defecto), guardada en `off_wait` para sobrevivir a un reinicio.
- La espera escucha los eventos de cambio de estado: en cuanto el PC se detecta `off`, la espera termina con resultado "apagado normal" **y no se reactiva aunque el PC vuelva a encenderse** (manualmente o por un encendido programado).
- Cualquier acción del panel o de un recordatorio durante la espera la cancela (el usuario tomó el control).
- Al cumplirse el plazo, si el PC está `on` (sin haberse detectado `off` en ningún momento) → pulso largo (`force_off`; permitido en `on` y `stopping`); con reintento único a los 10 s si el relé está ocupado.
- **Supresión del aviso intermedio**: el pulso corto abre la transición `stopping` habitual, que vence a los `TRANSITION_TIMEOUT_S` (120 s) con `no_effect`. Para ese pulso concreto el notificador ignora el `no_effect` mientras exista `off_wait`; al cerrar la espera se emite un único evento `scheduled_off_result` con `normal | forced | failed`, que sí se notifica. El historial registra todo.
- *Por qué una espera propia y no alargar `TRANSITION_TIMEOUT_S`*: ese valor y su comportamiento están especificados en `pc-power-status`; la espera de 10 min es una política del apagado programado, no del estado.

### D8. Recordatorio de apagado
Tarea asyncio que se despierta cada minuto (y ante cada cambio de estado). Estado en memoria: `on_since` (momento del último paso a `on`, tomado de la máquina), `first_sent`, `last_sent`.
- Primer recordatorio cuando `now - on_since >= REMINDER_AFTER_H` (4 por defecto).
- Tras el primero, a cada hora de `REMINDER_TIMES` (`21:00,06:00` por defecto, en `TZ`) mientras siga `on`, salvo que `now - last_sent < 30 min`.
- Al pasar a `off` se reinicia todo. Sin `NTFY_URL` la tarea no se crea.
- *Trade-off aceptado*: `on_since` vive en memoria; un reinicio de la Pi con el PC encendido reinicia el contador de 4 h (como mucho retrasa el primer aviso 4 h). Los recordatorios a horas fijas solo corren tras el primero.

### D9. Acciones en la notificación (Apagar / Mantener encendido)
Cada recordatorio se publica en ntfy con dos acciones de tipo `http` y `clear=true` (la app hace la petición y cierra la notificación):
- **Apagar** → `POST {PUBLIC_URL}/pc/r/<token>/off`
- **Mantener encendido** → `POST {PUBLIC_URL}/pc/r/<token>/keep`

Tokens:
- `secrets.token_urlsafe(32)` por recordatorio; en `reminders.json` se guarda solo `sha256(token)`, la caducidad y si está usado (escritura atómica, como `sessions.json`).
- Caducan al emitir el siguiente recordatorio o a las 12 h. `off` y `keep` consumen el token, salvo que `off` encuentre el relé ocupado: entonces el token sigue vivo para un reintento.
- `off` solo actúa si el estado es `on` (misma validación que `soft_off`); nunca fuerza ni enciende. `keep` solo registra el descarte.
- Respuesta: 204 si se aceptó; **404 vacío idéntico** para token inválido, usado, caducado o inventado, y para cualquier método distinto de POST. No se crea sesión ni se devuelve contenido.
- La ruta `/r/` está fuera de la puerta de acceso (la app ntfy no tiene la cookie): es la excepción declarada en el delta de `access-gate`. No exige `Origin`/`Sec-Fetch-Site` (no la llama un navegador); el token de 256 bits de un solo uso cumple esa función.
- Límite propio de 10 peticiones/min a `/r/` (404 silencioso al superarlo) para que no sirva de oráculo de fuerza bruta.
- `PUBLIC_URL` (p. ej. `https://mi-dominio.duckdns.org`) es obligatoria para incluir los botones: sin ella no hay a dónde apuntar un enlace, así que el recordatorio se envía solo con el texto de la pregunta y sin botones ni token útil.
- *Alternativa descartada*: un botón que solo abra el panel (más seguro, pero el usuario pidió apagar directamente desde la notificación).

### D6. Interfaz
Bajo el bloque de acciones:
- PC apagado: "Programar encendido" / "Encendido programado: 07:30 · Cancelar".
- PC encendido: "Programar apagado" / "Apagado programado: 23:00 · Cancelar"; durante la espera de forzado: "Esperando a que se apague (fuerza a las 23:10) · Cancelar".
- Hora actual de la Raspberry junto a las programaciones.
- Sección plegable "Actividad" con los últimos 50 eventos, que se carga al abrirla.

## Risks / Trade-offs

- [Encendido o apagado programado con un estado aparente erróneo (ICMP bloqueado)] → mismo riesgo y mitigación que el control básico.
- [**Quien lea el tema ntfy o vea la notificación puede apagar el PC una vez** con el botón del recordatorio] → token de un solo uso con caducidad corta, solo apagado normal, solo si el PC está encendido, todo queda en el historial y se notifica. Recomendación fuerte: tema con control de acceso (`NTFY_TOKEN`) o servidor ntfy propio.
- [El apagado forzado de respaldo pierde lo no guardado] → solo tras 10 min sin apagarse y nunca si el PC llegó a apagarse; aviso explícito del resultado.
- [Con el certificado autofirmado el botón Apagar falla en silencio en la app ntfy] → documentado; requiere dominio + Let's Encrypt (`SITE_ADDRESS` de la plataforma) y `PUBLIC_URL`.
- [Reinicio de la Pi reinicia el contador de 4 h] → aceptado (D8).
- [Reloj incorrecto tras corte de luz sin Internet] → la programación se descarta o se retrasa; se muestra la hora de la Raspberry.
- [Service worker que cachea de más] → network-only y `Cache-Control: no-store`; prueba sin conexión.
- [Más superficie de API] → rutas nuevas del panel tras la misma sesión y comprobación de origen; `/r/` con token, 404 uniforme y límite propio.

## Migration Plan

Aditivo. Sin `NTFY_URL` no hay notificaciones ni recordatorios; sin `PUBLIC_URL` el recordatorio se envía sin botones; sin programaciones no hay tareas. Reversión: desplegar la versión anterior; `events.jsonl`, `schedule.json` y `reminders.json` pueden quedarse o borrarse.
