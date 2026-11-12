# Tasks

Requisito previo: `add-pc-power-control` implementado y desplegado (archivado).

## 1. Eventos e historial

- [x] 1.1 Implementar `events.py` (emit/subscribe, aislamiento de errores de suscriptores) y añadir las llamadas `emit` en acción aceptada, cambio de estado, acción sin efecto, login correcto, logout y cruce del umbral de bloqueo. Verificar con pruebas que cada punto emite una vez y que un suscriptor que falla no interrumpe la acción
- [x] 1.2 Implementar el almacén de historial (`events.jsonl`, deque de 1000, rotación atómica, marca de cambio "externo") y verificar con pruebas: persistencia tras recargar, recorte al superar el límite, marca externa, y que ningún evento contiene el código enviado
- [x] 1.3 Añadir `GET ./api/events?limit=` (404 sin sesión) y la sección plegable "Actividad" del panel con horas relativas. Verificar con prueba de integración y en el navegador a 360 px que se listan los últimos 50 eventos en orden descendente

## 2. Notificaciones

- [x] 2.1 Implementar el notificador ntfy (cola acotada, tarea consumidora, timeout 5 s, tope 20/h, desactivado sin `NTFY_URL`, soporte de acciones `http`/`view` con `clear`) suscrito a los eventos de la spec. Verificar con pruebas usando un servidor HTTP falso: se envía cada evento esperado, un destino caído o lento no retrasa la acción, y el aviso 21 de la hora se descarta
- [x] 2.2 Documentar en `services/pc-power/README.md` la configuración de ntfy (tema aleatorio largo o con control de acceso, `NTFY_TOKEN`, app móvil) y añadir las variables a `deploy/env.example`; verificar en la Pi que al pulsar una acción llega el aviso al móvil

## 3. Instalación como app

- [x] 3.1 Añadir `manifest.webmanifest` (nombre neutro `APP_NAME`, standalone, rutas relativas), iconos 192/512, `apple-touch-icon`, metaetiquetas iOS y service worker network-only; ajustar la CSP si hace falta. Verificar con Lighthouse/DevTools que el sitio es instalable y que el manifiesto no menciona el PC
- [x] 3.2 Verificar en un móvil Android y/o iOS: añadir a la pantalla de inicio, abrir a pantalla completa con la sesión vigente, y en modo avión ver "Sin conexión" sin acciones habilitadas

## 4. Encendido programado

- [x] 4.1 Implementar el programador común (`schedule.json` con `on`/`off`, tareas asyncio, conversión HH:MM→próxima ocurrencia en `TZ`, descarte si vencida > 5 min, eventos `schedule_*` con `kind`) y el encendido: ejecución solo en `off`, un reintento si el relé está ocupado. Verificar con pruebas de reloj simulado todos los escenarios de la spec `power-schedule`
- [x] 4.2 Añadir `GET ./api/schedule` y `PUT/DELETE ./api/schedule/on` y la línea de encendido programado del panel (visible solo en `off`, con cancelar y hora actual de la Raspberry). Verificar con prueba de integración y manualmente con `RELAY_DRIVER=mock` programando a 2 minutos vista
- [x] 4.3 Documentar `TZ` y la programación en el README y `env.example`; verificar en la Pi con `timedatectl` que la hora y la sincronización NTP son correctas

## 5. Apagado programado

- [x] 5.1 Implementar el apagado programado sobre el programador común: pulso corto solo en `on`, espera de forzado `OFF_FORCE_AFTER_MIN` persistida en `off_wait`, fin de la espera al detectar `off` (sin reactivarse si vuelve a encender), cancelación ante cualquier acción del panel o de un recordatorio, pulso largo al vencer con reintento único, evento `scheduled_off_result`. Verificar con pruebas de reloj simulado todos los escenarios de la spec `power-off-schedule`, incluido "se apaga y se vuelve a encender" y la persistencia de la espera tras reiniciar
- [x] 5.2 Suprimir en el notificador el `no_effect` del pulso corto mientras exista `off_wait` y notificar una sola vez `scheduled_off_result`. Verificar con prueba que, con una espera de 10 min y transición de 120 s, solo llega un aviso al final (normal, forzado o fallido)
- [x] 5.3 Añadir `PUT/DELETE ./api/schedule/off` y la línea de apagado programado del panel (visible en `on`; durante la espera muestra la hora de forzado y permite cancelarla). Verificar con prueba de integración y manualmente con `RELAY_DRIVER=mock`, `OFF_FORCE_AFTER_MIN=1` y un PC simulado que no se apaga

## 6. Recordatorio de apagado

- [x] 6.1 Implementar el recordatorio (`REMINDER_AFTER_H`, `REMINDER_TIMES`, `on_since` desde la máquina, primer aviso, repetición a horas fijas en `TZ`, supresión si hubo aviso en los 30 min anteriores, reinicio al pasar a `off`, inactivo sin `NTFY_URL`). Verificar con pruebas de reloj simulado todos los escenarios de "Recordatorio tras horas encendido" y "Repetición a horas fijas"
- [x] 6.2 Implementar los enlaces de recordatorio (`reminders.json` con hash, caducidad al siguiente aviso o 12 h, un solo uso; el token sobrevive si el relé está ocupado) y las rutas `POST ./r/<token>/off|keep` fuera de la puerta de acceso, con 404 vacío uniforme y límite de 10/min. Verificar con pruebas: off con PC encendido acciona un pulso corto, off con PC apagado no acciona, reutilizado/caducado/inventado/GET dan el mismo 404, keep no acciona e invalida el token, no se crea sesión, y el resto de rutas sin sesión siguen dando 404 (delta de `access-gate`)
- [x] 6.3 Publicar los recordatorios con acciones ntfy `http` + `clear` (**Apagar** y **Mantener encendido**) cuando hay `PUBLIC_URL`, o solo con el texto y sin botones cuando no la hay; registrar en el historial el envío, el apagado y el descarte. Verificar con el servidor HTTP falso el JSON publicado (URLs, métodos, etiquetas) en ambos modos
- [x] 6.4 Documentar en el README `PUBLIC_URL`, `REMINDER_*`, `OFF_FORCE_AFTER_MIN`, el requisito de certificado válido para el botón directo y el riesgo del tema ntfy; añadir las variables a `env.example`. Verificar que los ejemplos del README coinciden con los valores por defecto del código

## 7. Verificación integral

- [x] 7.1 Desplegar con `scripts/deploy.sh pc-power` y recorrer en el móvil: programar un encendido real a pocos minutos, comprobar que el PC enciende, que llega la notificación y que el historial muestra programación, pulso y cambio de estado; reiniciar la Pi y comprobar que el historial persiste
- [x] 7.2 Con el PC encendido, programar un apagado real a pocos minutos y comprobar que se apaga con el pulso corto y llega un único aviso "apagado normal"; repetir con Windows bloqueando el apagado (p. ej. un documento sin guardar) y `OFF_FORCE_AFTER_MIN=2`, y comprobar que se fuerza y avisa "forzado"
- [x] 7.3 Con `REMINDER_AFTER_H` reducido temporalmente y dominio con certificado válido en `PUBLIC_URL`, comprobar en el móvil que llega el recordatorio con **Apagar** y **Mantener encendido**, que **Apagar** apaga el PC, que **Mantener encendido** no acciona nada y que reutilizar el enlace no hace nada; restaurar `REMINDER_AFTER_H=4`
