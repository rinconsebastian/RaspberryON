# access-gate Specification

## Purpose

Restringe el panel de control a los navegadores que han presentado el código de acceso correcto, sin dar a un atacante ninguna señal de si un intento fue acertado o fallido.

## Requirements

### Requirement: Código de acceso definido por entorno
El servicio SHALL tomar el código de acceso de una variable de entorno y SHALL negarse a arrancar si la variable falta o tiene menos de 8 caracteres.

#### Scenario: Variable ausente
- **WHEN** el servicio arranca sin código de acceso configurado
- **THEN** termina con un error en el registro del sistema y no atiende peticiones

#### Scenario: Código demasiado corto
- **WHEN** el servicio arranca con un código de 5 caracteres
- **THEN** termina con un error en el registro del sistema y no atiende peticiones

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

### Requirement: Autorización del navegador durante 30 días
Al recibir el código correcto, el servicio SHALL autorizar ese navegador durante 30 días sin volver a pedir el código, mediante una credencial que el JavaScript de la página no puede leer y que solo se envía por HTTPS al propio sitio.

#### Scenario: Código correcto
- **WHEN** el usuario envía el código correcto
- **THEN** ve el panel de control

#### Scenario: Regreso dentro del plazo
- **WHEN** el mismo navegador vuelve 29 días después
- **THEN** ve el panel sin que se le pida el código

#### Scenario: Regreso tras el plazo
- **WHEN** el mismo navegador vuelve 31 días después de autorizarse
- **THEN** se le pide el código de nuevo

#### Scenario: Reinicio del servicio
- **WHEN** el servicio o la Raspberry se reinician
- **THEN** los navegadores ya autorizados siguen autorizados

### Requirement: Respuesta indistinguible ante código incorrecto
Ante el envío de un código, el servicio SHALL responder con el mismo código de estado, el mismo cuerpo y el mismo mensaje genérico sea el código correcto, incorrecto o esté bloqueado por límite de intentos, y SHALL NOT mostrar ningún mensaje de error. El tiempo de respuesta SHALL NOT depender de cuántos caracteres coinciden.

#### Scenario: Código incorrecto
- **WHEN** el usuario envía un código incorrecto
- **THEN** vuelve a ver el formulario con el mensaje genérico "Solicitud recibida." y sin ninguna indicación de error

#### Scenario: Comparación de respuestas
- **WHEN** se comparan las respuestas al envío de un código correcto y de uno incorrecto
- **THEN** solo difieren en la presencia de la credencial de sesión

#### Scenario: Envío vacío
- **WHEN** el usuario envía el formulario vacío
- **THEN** recibe la misma respuesta genérica que con un código incorrecto

### Requirement: Limitación silenciosa de intentos
El servicio SHALL rechazar, con la misma respuesta genérica, todo envío de código procedente de una dirección que supere 5 intentos fallidos en 15 minutos, y todo envío de cualquier origen cuando haya más de 30 intentos fallidos globales en una hora, incluso si el código enviado es correcto.

#### Scenario: Sexto intento desde la misma dirección
- **WHEN** una dirección que acumula 5 fallos en los últimos 15 minutos envía el código correcto
- **THEN** recibe la respuesta genérica y no queda autorizada

#### Scenario: Fin del bloqueo
- **WHEN** han pasado 15 minutos desde el último fallo de esa dirección y envía el código correcto
- **THEN** queda autorizada

#### Scenario: Dirección real tras el proxy
- **WHEN** dos clientes con direcciones distintas acceden a través del punto de entrada
- **THEN** los intentos de cada uno se contabilizan por separado

### Requirement: Cierre de sesión
El panel SHALL permitir cerrar la sesión del navegador actual y cerrar la de todos los navegadores autorizados.

#### Scenario: Cerrar sesión en este navegador
- **WHEN** el usuario elige cerrar sesión
- **THEN** ese navegador vuelve a ver el formulario de código y los demás siguen autorizados

#### Scenario: Cerrar todas las sesiones
- **WHEN** el usuario elige cerrar todas las sesiones
- **THEN** todos los navegadores, incluido el actual, deben introducir el código de nuevo

### Requirement: Cambio de código invalida las sesiones
Cuando el código de acceso configurado cambia, el servicio SHALL invalidar todas las sesiones existentes.

#### Scenario: Rotación del código
- **WHEN** se cambia el código en la configuración y se reinicia el servicio
- **THEN** un navegador previamente autorizado ve el formulario de código

### Requirement: Protección contra peticiones de otros sitios
El servicio SHALL rechazar las peticiones que modifican estado (envío de código, acciones, cierre de sesión) cuyo origen no sea el propio sitio.

#### Scenario: Acción lanzada desde otra web
- **WHEN** una página de otro origen provoca una petición de acción en un navegador autorizado
- **THEN** la petición es rechazada y el relé no se acciona
