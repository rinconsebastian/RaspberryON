# Spec Delta

## Purpose

Determina si el PC controlado está encendido o apagado mediante ping a su IP local y mantiene ese estado disponible y actualizado para el panel.

## ADDED Requirements

### Requirement: Destino de monitoreo definido por entorno
El servicio SHALL tomar de una variable de entorno la dirección IP local del PC a monitorear y SHALL negarse a arrancar si falta o no es una dirección IP válida.

#### Scenario: Dirección ausente o inválida
- **WHEN** el servicio arranca sin la dirección del PC o con un valor que no es una IP
- **THEN** termina con un error en el registro del sistema

### Requirement: Detección de estado por ping
El servicio SHALL hacer ping al PC de forma continua, con un intervalo configurable (3 segundos por defecto), y SHALL considerar el PC encendido en cuanto recibe una respuesta y apagado tras 3 pings consecutivos sin respuesta.

#### Scenario: PC responde
- **WHEN** el PC responde a un ping
- **THEN** el estado pasa a "encendido"

#### Scenario: Pérdida aislada de un ping
- **WHEN** el PC está encendido y se pierde un único ping
- **THEN** el estado sigue siendo "encendido"

#### Scenario: PC deja de responder
- **WHEN** el PC no responde a 3 pings consecutivos
- **THEN** el estado pasa a "apagado"

#### Scenario: Recién arrancado el servicio
- **WHEN** el servicio acaba de arrancar y aún no ha completado la primera comprobación
- **THEN** el estado es "comprobando" y el panel no ofrece acciones hasta tener un estado

### Requirement: Estado en vivo en el panel
El panel SHALL mostrar el estado actual del PC y SHALL reflejar un cambio de estado en menos de 5 segundos desde que el servicio lo detecta, sin que el usuario recargue la página, mientras la página esté visible.

#### Scenario: El PC termina de arrancar con el panel abierto
- **WHEN** el estado pasa a "encendido" con el panel abierto
- **THEN** el panel muestra "Encendido" y las acciones correspondientes en menos de 5 segundos

#### Scenario: Pérdida de conexión con la Raspberry
- **WHEN** el panel no logra obtener el estado durante más de 10 segundos
- **THEN** muestra "Sin conexión" y deshabilita las acciones

### Requirement: Estados de transición tras una acción
Tras un pulso de encendido el servicio SHALL informar "encendiendo" hasta que el PC responda a ping, y tras un pulso de apagado o apagado forzado SHALL informar "apagando" hasta que deje de responder; si el cambio no ocurre en un tiempo máximo configurable (120 segundos por defecto), SHALL volver al estado detectado e indicar que la acción no surtió efecto.

#### Scenario: Encendido correcto
- **WHEN** se envía el pulso de encendido y el PC responde a ping 40 segundos después
- **THEN** el estado es "encendiendo" durante esos 40 segundos y luego "encendido"

#### Scenario: Apagado correcto
- **WHEN** se envía el pulso de apagado y el PC deja de responder 20 segundos después
- **THEN** el estado es "apagando" hasta entonces y luego "apagado"

#### Scenario: La acción no surte efecto
- **WHEN** se envía el pulso de encendido y el PC no responde en el tiempo máximo
- **THEN** el estado vuelve a "apagado" y el panel indica que el PC no cambió de estado

### Requirement: Momento del último cambio
El panel SHALL mostrar desde cuándo el PC se encuentra en el estado actual.

#### Scenario: PC encendido hace dos horas
- **WHEN** el estado es "encendido" desde hace dos horas
- **THEN** el panel muestra que lleva encendido aproximadamente 2 horas
