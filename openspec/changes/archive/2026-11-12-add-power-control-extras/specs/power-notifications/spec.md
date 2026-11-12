# Spec Delta

## Purpose

Avisa al dueño en su móvil, sin tener el panel abierto, de los eventos relevantes de control del PC y de seguridad del acceso.

## ADDED Requirements

### Requirement: Notificaciones opcionales configuradas por entorno
Las notificaciones SHALL estar desactivadas salvo que se configure por entorno un destino de notificación, y el servicio SHALL funcionar con normalidad cuando no hay destino configurado.

#### Scenario: Sin destino configurado
- **WHEN** no se configura destino de notificación
- **THEN** el servicio arranca y opera sin intentar enviar notificaciones

### Requirement: Eventos notificados
Con las notificaciones activas, el servicio SHALL enviar un aviso cuando se acepta una acción, cuando una acción no surte efecto, cuando se autoriza un navegador nuevo y cuando se produce un bloqueo por intentos fallidos. El pulso corto de un apagado programado no genera aviso de "sin efecto" mientras dure su espera de forzado; su resultado se avisa una sola vez al terminar (capacidad `power-off-schedule`).

#### Scenario: Navegador nuevo autorizado
- **WHEN** un navegador introduce el código correcto y queda autorizado
- **THEN** el móvil recibe un aviso con la hora y la dirección de origen

#### Scenario: Bloqueo por intentos
- **WHEN** una dirección alcanza el bloqueo por intentos fallidos
- **THEN** el móvil recibe un único aviso por ese bloqueo, no uno por intento

#### Scenario: Acción sin efecto
- **WHEN** se envió "Encender" y el PC no respondió en el tiempo máximo
- **THEN** el móvil recibe un aviso de que el PC no encendió

### Requirement: Las notificaciones no contienen secretos
Los avisos SHALL NOT incluir el código de acceso, códigos introducidos ni credenciales de sesión.

#### Scenario: Contenido del aviso de bloqueo
- **WHEN** se envía el aviso de bloqueo por intentos
- **THEN** contiene la dirección de origen y el número de intentos, y ningún código

### Requirement: El fallo de notificación no afecta al control
Un fallo o lentitud del destino de notificación SHALL NOT retrasar, bloquear ni hacer fallar las acciones, el acceso ni la monitorización.

#### Scenario: Sin salida a Internet
- **WHEN** la Raspberry no tiene salida a Internet y el usuario pulsa "Encender" desde la LAN
- **THEN** el relé se acciona con normalidad y el fallo de envío queda anotado en el registro del sistema

### Requirement: Límite de avisos
El servicio SHALL enviar como máximo 20 avisos por hora y SHALL descartar el exceso.

#### Scenario: Ataque sostenido
- **WHEN** se producen 100 bloqueos por intentos en una hora
- **THEN** el móvil recibe como máximo 20 avisos en esa hora
