# power-off-reminder Specification

## Purpose

Evita que el PC quede encendido por olvido: avisa por notificación push cuando lleva mucho tiempo encendido y permite apagarlo o descartar el aviso directamente desde la notificación.

## Requirements

### Requirement: Recordatorio tras horas encendido
Con las notificaciones activas, el servicio SHALL enviar un recordatorio cuando el PC lleve encendido de forma continua un número configurable de horas (4 por defecto), contadas desde que se detectó encendido.

#### Scenario: Cuatro horas encendido
- **WHEN** el PC lleva 4 horas encendido sin interrupción
- **THEN** el móvil recibe un recordatorio preguntando si se desea apagarlo

#### Scenario: Se apagó antes
- **WHEN** el PC se apaga a las 3 horas y vuelve a encenderse
- **THEN** el contador vuelve a empezar desde el nuevo encendido

#### Scenario: Notificaciones desactivadas
- **WHEN** no hay destino de notificación configurado
- **THEN** no se generan recordatorios

### Requirement: Repetición a horas fijas
Una vez enviado el primer recordatorio, y mientras el PC siga encendido, el servicio SHALL repetir el recordatorio indefinidamente a las horas configuradas (21:00 y 06:00 por defecto, en la zona horaria del servicio), y SHALL NOT enviar un recordatorio si ya envió otro en los 30 minutos anteriores.

#### Scenario: Sigue encendido por la noche
- **WHEN** el primer recordatorio se envió a las 15:00 y el PC sigue encendido
- **THEN** el móvil recibe recordatorios a las 21:00, a las 06:00 y así sucesivamente hasta que el PC se apague

#### Scenario: Coincide con el primer recordatorio
- **WHEN** el primer recordatorio se envía a las 20:45
- **THEN** no se envía otro a las 21:00 y el siguiente es el de las 06:00

#### Scenario: El PC se apaga
- **WHEN** el PC se detecta apagado
- **THEN** cesan los recordatorios hasta que vuelva a cumplir el plazo de horas encendido

### Requirement: Botones de respuesta en el recordatorio
Cuando el servicio tiene configurada su URL pública, cada recordatorio SHALL incluir dos botones: **Apagar**, que solicita el apagado normal (pulso corto), y **Mantener encendido**, que descarta ese recordatorio; ambos SHALL funcionar sin abrir el panel ni introducir el código. Sin URL pública el recordatorio SHALL enviarse sin botones.

#### Scenario: Apagar desde la notificación
- **WHEN** el usuario pulsa **Apagar** en un recordatorio vigente y el PC sigue encendido
- **THEN** el relé se acciona con un pulso corto, la notificación se cierra y el historial registra el apagado desde el recordatorio

#### Scenario: Mantener encendido
- **WHEN** el usuario pulsa **Mantener encendido**
- **THEN** el relé no se acciona, la notificación se cierra, el botón **Apagar** de ese recordatorio deja de funcionar y los recordatorios a horas fijas continúan

#### Scenario: Sin URL pública configurada
- **WHEN** el servicio no tiene URL pública configurada y se envía un recordatorio
- **THEN** el aviso llega con el texto de la pregunta y sin botones, y no se genera ningún enlace

#### Scenario: PC ya apagado al pulsar
- **WHEN** el usuario pulsa **Apagar** en un recordatorio pero el PC ya está apagado
- **THEN** el relé no se acciona

### Requirement: Enlaces de recordatorio de un solo uso
Cada recordatorio SHALL llevar un enlace secreto propio, impredecible, válido para un único uso y que caduca con el siguiente recordatorio o a las 12 horas, lo que ocurra antes. El enlace SHALL permitir únicamente el apagado normal o el descarte, nunca el apagado forzado, el encendido ni el acceso al panel.

#### Scenario: Enlace reutilizado
- **WHEN** se usa por segunda vez el enlace de un recordatorio
- **THEN** la respuesta es 404 y el relé no se acciona

#### Scenario: Enlace caducado o inventado
- **WHEN** se usa un enlace caducado, de un recordatorio anterior o inventado
- **THEN** la respuesta es 404, idéntica en todos los casos, y el relé no se acciona

#### Scenario: El enlace no abre el panel
- **WHEN** se usa un enlace de recordatorio válido
- **THEN** no se crea ninguna sesión de navegador

### Requirement: Respeto de las salvaguardas del relé
El apagado solicitado desde un recordatorio SHALL respetar las mismas salvaguardas que el panel: validación contra el estado actual y un solo accionamiento a la vez.

#### Scenario: Relé ocupado
- **WHEN** se pulsa **Apagar** en un recordatorio mientras hay un pulso en curso o en enfriamiento
- **THEN** el relé no se acciona de nuevo y el enlace sigue siendo válido para un reintento
