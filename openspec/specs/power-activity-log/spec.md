# power-activity-log Specification

## Purpose

Mantiene un registro consultable desde el panel de lo que ha ocurrido con el PC y con el acceso al sitio, para poder saber quién accionó qué y cuándo.

## Requirements

### Requirement: Registro de eventos de control y acceso
El servicio SHALL registrar, con fecha, hora y dirección de origen cuando aplique, cada acción aceptada, cada cambio de estado del PC, cada acción que no surtió efecto, cada navegador nuevo autorizado, cada cierre de sesión y cada bloqueo por intentos fallidos.

#### Scenario: Acción desde el panel
- **WHEN** un navegador autorizado envía "Encender"
- **THEN** el historial contiene una entrada con la acción, la hora y la dirección de origen

#### Scenario: Cambio de estado no provocado desde el panel
- **WHEN** el PC pasa a "apagado" sin que haya una acción reciente del panel
- **THEN** el historial contiene una entrada de cambio de estado marcada como externa

#### Scenario: Intentos fallidos
- **WHEN** una dirección alcanza el bloqueo por intentos fallidos
- **THEN** el historial contiene una única entrada de bloqueo con la dirección y el número de intentos

### Requirement: El registro nunca contiene secretos
El historial SHALL NOT almacenar el código de acceso, los códigos introducidos (correctos o no) ni las credenciales de sesión.

#### Scenario: Código erróneo introducido
- **WHEN** alguien envía un código incorrecto
- **THEN** ningún registro persistente contiene el texto enviado

### Requirement: Consulta del historial en el panel
El panel SHALL mostrar a los navegadores autorizados los eventos más recientes, del más nuevo al más antiguo, con hora legible y descripción, y SHALL NOT exponer el historial a navegadores sin sesión.

#### Scenario: Ver historial
- **WHEN** el usuario abre el historial en el panel
- **THEN** ve al menos los últimos 50 eventos ordenados del más reciente al más antiguo

#### Scenario: Sin sesión
- **WHEN** un cliente sin sesión solicita el historial
- **THEN** recibe 404

### Requirement: Retención acotada y persistente
El historial SHALL sobrevivir a reinicios del servicio y de la Raspberry, y SHALL conservar como máximo los últimos 1000 eventos, descartando los más antiguos.

#### Scenario: Reinicio
- **WHEN** la Raspberry se reinicia
- **THEN** los eventos anteriores siguen visibles en el panel

#### Scenario: Límite alcanzado
- **WHEN** se registra el evento 1001
- **THEN** el evento más antiguo deja de estar almacenado
