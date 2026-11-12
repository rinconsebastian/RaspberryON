# Spec Delta

## MODIFIED Requirements

### Requirement: Solicitud de código en navegadores no autorizados
El servicio SHALL mostrar únicamente un formulario de código a todo navegador sin sesión válida, y SHALL NOT mostrarle el estado del PC, las acciones ni ningún texto que describa para qué sirve el sitio. La única acción admitida sin sesión es la solicitada mediante un enlace de recordatorio válido (capacidad `power-off-reminder`), limitada al apagado normal o al descarte del recordatorio.

#### Scenario: Primer acceso
- **WHEN** un navegador sin sesión abre el sitio
- **THEN** ve un formulario con un único campo de código y sin información sobre el PC

#### Scenario: Llamada directa a una acción sin sesión
- **WHEN** un cliente sin sesión válida invoca la consulta de estado o una acción
- **THEN** recibe 404 y el relé no se acciona

#### Scenario: Enlace de recordatorio válido
- **WHEN** un cliente sin sesión usa el enlace vigente de un recordatorio para solicitar el apagado
- **THEN** se envía el apagado normal si el PC está encendido, sin crear sesión ni mostrar el panel, y cualquier otra acción sin sesión sigue recibiendo 404
