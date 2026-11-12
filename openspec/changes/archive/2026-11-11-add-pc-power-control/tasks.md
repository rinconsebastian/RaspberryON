# Tasks

Requisito previo: `setup-pi-service-platform` aplicado (proxy, `scripts/deploy.sh`, acceso SSH por llave).

## 1. Verificación de hardware y entorno

- [x] 1.1 Confirmar en la Pi que `python3 -m venv --help` y `ping -c 1 <IP del PC>` funcionan sin root (Python 3.13, gpiozero y lgpio ya están); instalar `python3-venv` si falta. Verificar que ambos comandos terminan con código 0
- [x] 1.2 Con el relé **desconectado del PC**, determinar la polaridad (indicio previo: GPIO23 lee alto en reposo → probablemente activo en bajo): accionar GPIO23 con `pinctrl set 23 op dh` / `dl` y observar el clic/LED del módulo. Registrar el resultado en `services/pc-power/README.md` y verificar que el relé queda abierto en el nivel de reposo anotado
- [x] 1.3 Dejar GPIO23 como entrada en el arranque, sin ninguna línea `gpio=` en `/boot/firmware/config.txt` (design D2: el módulo es activo en bajo y solo se abre soltando el pin), reiniciar y verificar que `pinctrl get 23` muestra `ip` y que el relé no hace clic durante el arranque
- [x] 1.4 Verificar que el PC responde a ping encendido y no responde apagado (en Windows, habilitar la regla de firewall "Archivos e impresoras compartidos (petición eco: ICMPv4 de entrada)") y que tiene IP fija o reserva DHCP; anotar la IP

## 2. Esqueleto del servicio y configuración

- [x] 2.1 Crear `services/pc-power/` (`app/`, `static/`, `tests/`, `deploy/`, `requirements.txt` con fastapi y uvicorn, `pyproject.toml` con pytest) y verificar que `pytest` se ejecuta (0 pruebas) en el PC de desarrollo
- [x] 2.2 Implementar `config.py` (variables de design D11 con validación: código ≥ 8, `PC_HOST` IP válida, límites de pulso) con pruebas unitarias de cada caso de rechazo; verificar que las pruebas pasan y que arrancar sin `ACCESS_CODE` termina con error

## 3. Relé

- [x] 3.1 Implementar `relay.py` con interfaz común y dos drivers (`gpio` con gpiozero, `mock` que registra tiempos): pulso con `try/finally`, cerrojo, cooldown de 5 s, estado inicial abierto. Verificar con pruebas sobre el mock: duración del pulso, rechazo concurrente, rechazo en cooldown, apertura tras excepción
- [x] 3.2 Probar el driver `gpio` en la Pi con un script manual (relé aún desconectado del PC): pulso corto y largo, y `kill -9` a mitad de pulso largo. Verificar por clic/LED que las duraciones son correctas y que el relé queda abierto tras el kill

## 4. Monitor de estado

- [x] 4.1 Implementar `monitor.py` (bucle de ping por subproceso, función de ping inyectable) y `power.py` (máquina de estados de design D4 con `since`, transiciones, timeout y aviso "sin efecto"). Verificar con pruebas de reloj simulado: 1 ok → on, 3 fallos → off, 1 fallo aislado no cambia, starting→on, stopping→off, timeout con aviso, estado inicial `checking`
- [x] 4.2 Implementar la validación de acciones contra estado (qué acción se admite en cada estado) y verificar con pruebas la tabla completa acción × estado

## 5. Puerta de acceso

- [x] 5.1 Implementar el almacén de sesiones (token aleatorio, hash en `sessions.json`, escritura atómica, expiración a 30 días, huella del código, cerrar una / cerrar todas). Verificar con pruebas: persistencia tras recargar, caducidad, invalidación al cambiar el código
- [x] 5.2 Implementar el limitador de intentos (5/15 min por IP, 30/h global, IP desde `X-Forwarded-For` solo si el par es 127.0.0.1). Verificar con pruebas de reloj simulado ambos umbrales, el desbloqueo y que una cabecera falsificada desde un par no local se ignora
- [x] 5.3 Implementar `POST ./login` con respuesta uniforme (303 a `./?s=1`, mismo cuerpo, tiempo fijo, comparación en tiempo constante) y la cookie de design D7. Verificar con pruebas que las respuestas a código correcto, incorrecto, vacío y bloqueado son idénticas salvo `Set-Cookie`, y que el código correcto bajo bloqueo no crea sesión
- [x] 5.4 Implementar la protección de rutas (404 sin sesión en `./api/*`), la comprobación de `Origin` en POST y las cabeceras de seguridad de D9. Verificar con pruebas: API sin cookie → 404, POST con `Origin` ajeno → rechazado, cabeceras presentes

## 6. API y panel

- [x] 6.1 Implementar `GET ./api/status`, `POST ./api/action`, `POST ./api/logout` y `./api/logout-all` conectando auth, estado y relé (driver mock en pruebas). Verificar con pruebas de integración: flujo login → status → power_on → 409 al repetir → transición → logout
- [x] 6.2 Construir el formulario de código (neutro, sin mención al PC, mensaje "Solicitud recibida." con `?s=1`) y verificar manualmente que un código erróneo y uno vacío muestran exactamente lo mismo
- [x] 6.3 Construir el panel (`static/`): estado y antigüedad, botón principal según estado, "Forzar apagado" con mantener-pulsado 2 s, opciones secundarias, botones deshabilitados en ocupado/transición/sin conexión, sondeo cada 2 s solo con la página visible, tema claro/oscuro, URLs relativas. Verificar en el navegador con `RELAY_DRIVER=mock` a 360 px de ancho: sin scroll horizontal, botones ≥ 48 px, cada estado muestra las acciones de la spec
- [x] 6.4 Escribir `services/pc-power/README.md`: variables de entorno, cableado y polaridad, requisito de ICMP en el PC, cómo rotar el código, cómo ejecutar en local con el mock; verificar que el comando de ejecución local documentado arranca el servicio

## 7. Despliegue en la Raspberry

- [x] 7.1 Crear `deploy/service.unit` (usuario `svc-pc-power`, grupo `gpio`, `DeviceAllow=/dev/gpiochip0 rw`, sin restringir `CAP_NET_RAW`, `StateDirectory`, un solo worker en 127.0.0.1:8101), `deploy/route.caddy` (`/pc`), `deploy/env.example` e `install.sh` (venv con `--system-site-packages` + requirements); registrar el puerto en `platform/PORTS.md`. Verificar con `scripts/deploy.sh pc-power` que el servicio queda `active`
- [x] 7.2 Configurar `/etc/raspberryon/pc-power.env` en la Pi (código real, IP del PC, polaridad de 1.2) y verificar con `journalctl -u raspberryon-pc-power` que arranca sin errores, hace ping y no acciona el relé al arrancar ni al reiniciar el servicio

## 8. Verificación integral

- [x] 8.1 Con el relé aún desconectado del PC, recorrer desde el móvil en la LAN (`https://192.168.10.239/pc/`): código erróneo → mensaje genérico; código correcto → panel; cerrar y reabrir el navegador → sigue autorizado; pulso corto y largo → clic con la duración correcta
- [x] 8.2 Conectar el relé al pulsador del PC y verificar el ciclo real: Encender → "Encendiendo…" → "Encendido"; Apagar → "Apagando…" → "Apagado"; Forzar apagado con el PC encendido lo corta en ~4–6 s
- [x] 8.3 Verificar resistencia: 6 códigos erróneos seguidos y luego el correcto → sigue sin acceso hasta pasar 15 min (o reiniciar el servicio); reiniciar la Pi con el PC encendido → el PC no se apaga y el navegador sigue autorizado
