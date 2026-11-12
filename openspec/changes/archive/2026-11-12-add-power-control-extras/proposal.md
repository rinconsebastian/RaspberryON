# Proposal

## Why

Un botón que enciende y apaga el PC desde Internet merece saber quién lo usó y cuándo, y enterarse si alguien está probando códigos. Además, abrirlo desde el móvil debería ser tan rápido como abrir una app, y el PC no debería quedarse encendido horas por olvido. Son mejoras opcionales sobre `add-pc-power-control`, separadas para poder aceptarlas, recortarlas o descartarlas sin afectar al control básico.

## What Changes

- **Historial de actividad** en el panel: acciones enviadas, cambios de estado del PC (incluidos los no provocados desde el panel, p. ej. un corte de luz o un encendido manual), nuevos navegadores autorizados y rachas de intentos fallidos, con fecha y dirección de origen.
- **Notificaciones push al móvil** (opcionales, se activan por variable de entorno): acción ejecutada, nuevo navegador autorizado, bloqueo por intentos fallidos y acción que no surtió efecto.
- **Instalable como app** en la pantalla de inicio del móvil (icono propio, pantalla completa, sin barra del navegador).
- **Encendido programado de un solo uso**: "encender a las HH:MM" para tener el PC listo al llegar, cancelable desde el panel.
- **Apagado programado de un solo uso**: "apagar a las HH:MM". Envía el apagado normal y, si el PC sigue encendido tras una espera de hasta 10 minutos (las actualizaciones de Windows pueden retrasar el apagado), lo fuerza. No fuerza si en ese intervalo el PC llegó a apagarse, aunque luego se vuelva a encender.
- **Recordatorio de apagado**: si el PC lleva más de 4 horas encendido de forma continua, una notificación push pregunta si se desea apagarlo, con dos botones: **Apagar** (apagado normal directo desde la notificación) y **Mantener encendido**. Mientras siga encendido, el recordatorio se repite indefinidamente a las 21:00 y a las 06:00.
- **BREAKING (acotado)** para `access-gate`: el botón **Apagar** de la notificación acciona el relé sin sesión de navegador, mediante un enlace secreto de un solo uso; es la única excepción a "sin sesión no se acciona nada".

## Capabilities

### New Capabilities
- `power-activity-log`: registro persistente y consulta desde el panel de acciones, cambios de estado y eventos de acceso.
- `power-notifications`: avisos push opcionales al móvil sobre eventos relevantes de control y de seguridad.
- `power-panel-install`: instalación del panel como aplicación en la pantalla de inicio del móvil.
- `power-schedule`: programación de un encendido único a una hora futura.
- `power-off-schedule`: programación de un apagado único a una hora futura, con forzado de respaldo.
- `power-off-reminder`: recordatorios push para apagar un PC que lleva mucho tiempo encendido, con respuesta directa desde la notificación.

### Modified Capabilities
- `access-gate`: el requisito que niega toda acción sin sesión admite una excepción: un enlace de recordatorio válido puede solicitar el apagado normal o descartar el recordatorio.

## Impact

- **Repo**: nuevos módulos en `services/pc-power/app/` (eventos, historial, notificador, programador, recordatorio), manifiesto e iconos en `static/`, nuevas secciones en el panel, ruta pública de enlaces de recordatorio.
- **Raspberry Pi**: archivos nuevos en `/var/lib/raspberryon/pc-power/` (historial, programaciones pendientes, enlaces de recordatorio); variables nuevas opcionales en `pc-power.env` (`NTFY_URL`, `NTFY_TOKEN`, `TZ`, `PUBLIC_URL`, `REMINDER_AFTER_H`, `REMINDER_TIMES`, `OFF_FORCE_AFTER_MIN`).
- **Dependencia externa opcional**: un servidor ntfy (el público `ntfy.sh` o uno propio) y la app ntfy en el móvil; la Raspberry necesita salida a Internet para notificar.
- **Botón Apagar de la notificación**: la Raspberry debe ser alcanzable desde Internet en `PUBLIC_URL` con un **certificado válido** (dominio + Let's Encrypt, ver plataforma); con el certificado autofirmado la app ntfy rechaza la petición.
- **Depende de**: `add-pc-power-control` (implementado y archivado).
