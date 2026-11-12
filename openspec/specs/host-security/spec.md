# host-security Specification

## Purpose

Define la superficie de red y el acceso administrativo de la Raspberry Pi para que pueda exponerse a Internet mediante NAT con un riesgo acotado.

## Requirements

### Requirement: Superficie de red mínima
El host SHALL aceptar conexiones entrantes únicamente en los puertos 80 y 443 desde cualquier origen y en el puerto SSH desde la red local, y SHALL descartar el resto del tráfico entrante.

#### Scenario: Puerto no publicado
- **WHEN** un equipo intenta conectar a un puerto distinto de 22, 80 o 443 de la Raspberry
- **THEN** la conexión no se establece

#### Scenario: SSH desde fuera de la LAN
- **WHEN** llega una conexión SSH con origen fuera de la subred local
- **THEN** la conexión no se establece

### Requirement: Acceso SSH solo con llave
El host SHALL aceptar sesiones SSH únicamente con autenticación por llave pública, y SHALL NOT desactivar la autenticación por contraseña hasta haber comprobado que el acceso por llave funciona.

#### Scenario: Intento con contraseña
- **WHEN** un cliente intenta autenticarse por SSH con contraseña tras el endurecimiento
- **THEN** el servidor rechaza el método de autenticación

#### Scenario: Llave no verificada
- **WHEN** el aprovisionamiento no logra comprobar una sesión SSH por llave
- **THEN** la autenticación por contraseña permanece habilitada y el aprovisionamiento lo informa

### Requirement: Actualizaciones de seguridad automáticas
El host SHALL instalar automáticamente las actualizaciones de seguridad del sistema operativo sin intervención manual.

#### Scenario: Actualización de seguridad disponible
- **WHEN** el repositorio del sistema publica una actualización de seguridad
- **THEN** se instala automáticamente dentro de las siguientes 24 horas
