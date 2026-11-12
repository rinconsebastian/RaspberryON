# Spec Delta

## Purpose

Permite añadir el panel a la pantalla de inicio del móvil y abrirlo como una aplicación, sin barra del navegador.

## ADDED Requirements

### Requirement: Panel instalable en la pantalla de inicio
El panel SHALL poder añadirse a la pantalla de inicio en Android (Chrome) e iOS (Safari) con icono y nombre propios, y al abrirse desde ahí SHALL mostrarse a pantalla completa sin la interfaz del navegador.

#### Scenario: Abrir desde el icono
- **WHEN** el usuario abre el panel desde el icono de la pantalla de inicio
- **THEN** el panel se muestra a pantalla completa sin barra de direcciones

#### Scenario: Sesión compartida con el plazo normal
- **WHEN** el usuario abre el panel instalado dentro de los 30 días desde que autorizó ese navegador
- **THEN** ve el panel sin que se le pida el código

### Requirement: Sin datos del panel fuera de línea
El panel instalado SHALL NOT mostrar un estado del PC guardado cuando no puede contactar con la Raspberry; SHALL indicar que no hay conexión.

#### Scenario: Sin cobertura
- **WHEN** el usuario abre el panel instalado sin conexión
- **THEN** ve "Sin conexión" y ninguna acción habilitada

### Requirement: La instalación no revela el propósito a navegadores sin sesión
Los metadatos de instalación accesibles sin sesión SHALL usar un nombre neutro que no describa la función del sitio.

#### Scenario: Metadatos sin sesión
- **WHEN** un cliente sin sesión obtiene los metadatos de instalación
- **THEN** el nombre y la descripción no mencionan el PC ni el control de encendido
