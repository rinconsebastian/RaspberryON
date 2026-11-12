# service-hosting Specification

## Purpose

Permite alojar varios servicios web independientes en la misma Raspberry Pi detrás de un único punto de entrada HTTPS, con una convención común de aislamiento, configuración y despliegue.

## Requirements

### Requirement: Punto de entrada HTTPS único
La plataforma SHALL exponer todos los servicios web a través de un único punto de entrada en el puerto 443 con TLS, y SHALL redirigir a HTTPS cualquier petición recibida por HTTP en el puerto 80.

#### Scenario: Petición por HTTP
- **WHEN** un cliente pide `http://<host>/pc/`
- **THEN** recibe una redirección a `https://<host>/pc/`

#### Scenario: Petición por HTTPS a un servicio registrado
- **WHEN** un cliente pide `https://<host>/pc/`
- **THEN** la respuesta la genera el servicio registrado bajo el prefijo `/pc`

### Requirement: Modo TLS configurable
La plataforma SHALL servir un certificado autofirmado cuando no hay dominio configurado, y SHALL obtener y renovar automáticamente un certificado públicamente confiable cuando se configura un dominio, sin cambios en los servicios.

#### Scenario: Sin dominio configurado
- **WHEN** no se ha configurado un dominio y un cliente accede por IP
- **THEN** la conexión se cifra con un certificado autofirmado

#### Scenario: Dominio configurado
- **WHEN** se configura un dominio que resuelve a la IP pública y el puerto 443 externo llega a la Raspberry
- **THEN** el navegador muestra la conexión como segura sin advertencias

### Requirement: Enrutamiento por prefijo de ruta
Cada servicio SHALL publicarse bajo un prefijo de ruta propio, y añadir o quitar un servicio SHALL NOT requerir modificar la configuración de los demás servicios.

#### Scenario: Alta de un segundo servicio
- **WHEN** se despliega un servicio nuevo con prefijo `/otro`
- **THEN** `https://<host>/otro/` responde el servicio nuevo y `https://<host>/pc/` sigue respondiendo sin cambios

#### Scenario: Prefijo sin barra final
- **WHEN** un cliente pide `https://<host>/pc`
- **THEN** recibe una redirección a `https://<host>/pc/`

### Requirement: Rutas desconocidas no revelan información
La plataforma SHALL responder a cualquier ruta que no pertenezca a un servicio registrado con un 404 de cuerpo vacío, y SHALL NOT incluir cabeceras ni contenido que identifiquen el software o enumeren los servicios.

#### Scenario: Ruta raíz
- **WHEN** un cliente pide `https://<host>/`
- **THEN** recibe 404 con cuerpo vacío y sin listado de servicios

### Requirement: Servicios aislados y no accesibles directamente
Cada servicio SHALL ejecutarse con un usuario de sistema propio sin privilegios y SHALL escuchar únicamente en la interfaz local, de modo que solo sea alcanzable a través del punto de entrada.

#### Scenario: Acceso directo al puerto del servicio
- **WHEN** un equipo de la LAN intenta conectar al puerto interno de un servicio en la IP de la Raspberry
- **THEN** la conexión es rechazada

### Requirement: Configuración por archivo de entorno fuera del repositorio
Cada servicio SHALL leer su configuración y secretos de un archivo de entorno propio en la Raspberry, legible solo por root y por el usuario del servicio, y el repositorio SHALL contener únicamente un ejemplo sin valores secretos.

#### Scenario: Permisos del archivo de entorno
- **WHEN** otro usuario sin privilegios intenta leer el archivo de entorno de un servicio
- **THEN** el sistema deniega la lectura

#### Scenario: Despliegue no sobrescribe secretos
- **WHEN** se vuelve a desplegar un servicio cuyo archivo de entorno ya existe
- **THEN** el archivo de entorno existente se conserva intacto

### Requirement: Arranque automático y recuperación
Los servicios y el punto de entrada SHALL iniciarse automáticamente al arrancar la Raspberry y SHALL reiniciarse automáticamente si su proceso termina de forma inesperada.

#### Scenario: Reinicio de la Raspberry
- **WHEN** la Raspberry se reinicia por un corte de energía
- **THEN** los servicios vuelven a estar disponibles sin intervención manual

#### Scenario: Caída de un servicio
- **WHEN** el proceso de un servicio termina de forma inesperada
- **THEN** se reinicia automáticamente en menos de 10 segundos

### Requirement: Despliegue repetible desde el equipo de desarrollo
La plataforma SHALL permitir aprovisionar el host y desplegar o actualizar un servicio con un único comando por operación desde el equipo de desarrollo, y repetir cualquiera de ellos SHALL dejar el sistema en el mismo estado.

#### Scenario: Aprovisionamiento repetido
- **WHEN** se ejecuta el aprovisionamiento dos veces seguidas
- **THEN** la segunda ejecución termina sin errores y sin cambiar el comportamiento del sistema

#### Scenario: Actualización de un servicio
- **WHEN** se ejecuta el despliegue de un servicio tras cambiar su código
- **THEN** el servicio queda ejecutando la versión nueva y el comando informa si el servicio quedó activo
