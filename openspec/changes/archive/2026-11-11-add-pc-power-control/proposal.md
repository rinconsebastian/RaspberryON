# Proposal

## Why

Quiero encender, apagar y forzar el apagado de mi PC desde el móvil, esté en casa o fuera. La Raspberry Pi tiene un relé en GPIO23 cableado en paralelo al pulsador de encendido del PC; falta el sitio web que lo accione de forma segura, sabiendo en cada momento si el PC está encendido.

## What Changes

- Nuevo servicio web `pc-power`, pensado para móvil, publicado bajo `/pc/` en la plataforma de `setup-pi-service-platform`.
- **Puerta de acceso por código**: el primer acceso desde un navegador pide un código definido por variable de entorno; al acertar, el navegador queda autorizado 30 días. Un código incorrecto no produce error: la respuesta es idéntica y genérica. Incluye limitación de intentos silenciosa, porque el sitio quedará expuesto por NAT.
- **Estado del PC por ping** a una IP local definida por variable de entorno, mostrado en vivo.
- **Acciones según estado**:
  - PC apagado → **Encender** (pulso corto).
  - PC encendido → **Apagar** (pulso corto) y **Forzar apagado** (pulso largo, con confirmación).
  - Caso añadido: PC colgado que ya no responde a ping → opción secundaria de pulso largo también disponible en estado "apagado".
- Estados de transición ("Encendiendo…", "Apagando…") y bloqueo de acciones simultáneas para evitar dobles pulsaciones.
- Seguridad física del relé: nunca queda cerrado tras un fallo o reinicio; duración de pulso acotada.
- Cierre de sesión del navegador actual y de todos los navegadores.

## Capabilities

### New Capabilities
- `access-gate`: autorización de navegadores mediante código compartido, sesión de 30 días, respuesta indistinguible ante códigos erróneos y limitación de intentos.
- `pc-power-status`: detección por ping del estado encendido/apagado del PC y su exposición al panel, incluidos los estados de transición.
- `pc-power-actions`: panel móvil y accionamiento del relé (pulso corto/largo) según el estado, con sus salvaguardas.

### Modified Capabilities

Ninguna.

## Impact

- **Repo**: nuevo `services/pc-power/` (aplicación Python, interfaz web estática, pruebas, archivos de despliegue); entrada 8101 en `platform/PORTS.md`.
- **Raspberry Pi**: servicio `raspberryon-pc-power`, usuario `svc-pc-power` en el grupo `gpio`, `/etc/raspberryon/pc-power.env`, estado en `/var/lib/raspberryon/pc-power/`; posible línea en `/boot/firmware/config.txt` para fijar el nivel de GPIO23 en el arranque.
- **PC controlado**: debe responder a ping (en Windows hay que permitir ICMPv4 entrante en el firewall) y tener IP fija o reserva DHCP.
- **Depende de**: `setup-pi-service-platform` (proxy HTTPS y convención de despliegue).
- **Por confirmar**: polaridad del módulo de relé. GPIO23 lee nivel alto en reposo, lo que apunta a un módulo activo en bajo; se configura por variable obligatoria y se verifica con el relé desconectado del PC antes de cablear.
