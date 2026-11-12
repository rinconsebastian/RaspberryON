# power-schedule Specification

## Purpose

Permite dejar programado un encendido único del PC a una hora futura, para encontrarlo listo sin tener que abrir el panel en ese momento.

## Requirements

### Requirement: Programar un encendido único
Con el PC apagado, el panel SHALL permitir programar un único encendido a una hora dentro de las próximas 24 horas, y SHALL mostrar la programación pendiente con su hora.

#### Scenario: Programar
- **WHEN** el estado es "apagado" y el usuario programa el encendido para las 07:30
- **THEN** el panel muestra "Encendido programado: 07:30"

#### Scenario: Ya hay una programación
- **WHEN** existe una programación pendiente y el usuario programa otra hora
- **THEN** la nueva hora sustituye a la anterior

### Requirement: Ejecución condicionada al estado
A la hora programada el servicio SHALL enviar el pulso de encendido solo si el PC está apagado en ese momento; si está encendido SHALL descartar la programación sin accionar el relé.

#### Scenario: PC apagado a la hora programada
- **WHEN** llega la hora programada y el estado es "apagado"
- **THEN** el relé se acciona con un pulso corto y la programación queda consumida

#### Scenario: PC ya encendido
- **WHEN** llega la hora programada y el estado es "encendido"
- **THEN** el relé no se acciona y la programación queda descartada

### Requirement: Cancelación
El panel SHALL permitir cancelar la programación pendiente.

#### Scenario: Cancelar
- **WHEN** el usuario cancela la programación antes de su hora
- **THEN** el relé no se acciona a esa hora y el panel deja de mostrarla

### Requirement: Persistencia y horas vencidas
La programación pendiente SHALL sobrevivir a un reinicio del servicio, y una programación cuya hora pasó hace más de 5 minutos mientras el servicio no estaba en ejecución SHALL descartarse sin accionar el relé.

#### Scenario: Reinicio antes de la hora
- **WHEN** la Raspberry se reinicia una hora antes de la hora programada
- **THEN** el encendido se ejecuta a su hora

#### Scenario: Raspberry apagada durante la hora programada
- **WHEN** el servicio arranca 2 horas después de la hora programada
- **THEN** la programación se descarta y el relé no se acciona

### Requirement: Hora en la zona horaria del usuario
Las horas de programación SHALL interpretarse y mostrarse en la zona horaria configurada para el servicio.

#### Scenario: Programar a las 07:30
- **WHEN** el usuario programa las 07:30 con la zona configurada America/Bogota
- **THEN** el encendido ocurre a las 07:30 de Bogotá
