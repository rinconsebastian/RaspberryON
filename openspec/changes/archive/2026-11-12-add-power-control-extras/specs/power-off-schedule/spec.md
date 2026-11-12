# Spec Delta

## Purpose

Permite dejar programado un apagado único del PC a una hora futura, con un apagado forzado de respaldo si el apagado normal no surte efecto en un plazo razonable.

## ADDED Requirements

### Requirement: Programar un apagado único
Con el PC encendido, el panel SHALL permitir programar un único apagado a una hora dentro de las próximas 24 horas, y SHALL mostrar la programación pendiente con su hora. Una nueva programación SHALL sustituir a la anterior.

#### Scenario: Programar
- **WHEN** el estado es "encendido" y el usuario programa el apagado para las 23:00
- **THEN** el panel muestra "Apagado programado: 23:00"

#### Scenario: Ya hay un apagado programado
- **WHEN** existe un apagado programado y el usuario programa otra hora
- **THEN** la nueva hora sustituye a la anterior

#### Scenario: Convive con el encendido programado
- **WHEN** hay un encendido programado para las 07:30 y el usuario programa un apagado para las 23:00
- **THEN** ambas programaciones quedan pendientes y se muestran

### Requirement: Apagado normal a la hora programada
A la hora programada, si el PC está encendido, el servicio SHALL enviar el apagado normal (pulso corto); si el PC está apagado SHALL descartar la programación sin accionar el relé.

#### Scenario: PC encendido a la hora programada
- **WHEN** llega la hora programada y el estado es "encendido"
- **THEN** el relé se acciona con un pulso corto y comienza la espera de forzado

#### Scenario: PC ya apagado
- **WHEN** llega la hora programada y el estado es "apagado"
- **THEN** el relé no se acciona y la programación queda descartada

### Requirement: Apagado forzado de respaldo
Tras el pulso corto de un apagado programado, el servicio SHALL esperar hasta un plazo configurable (10 minutos por defecto) y, solo si el PC sigue encendido al terminarlo y no se detectó apagado en ningún momento desde el pulso corto, SHALL enviar un apagado forzado (pulso largo).

#### Scenario: Windows tarda pero se apaga
- **WHEN** tras el pulso corto el PC deja de responder a los 7 minutos
- **THEN** no se envía el pulso largo

#### Scenario: El PC no se apaga
- **WHEN** tras el pulso corto el PC sigue encendido al cumplirse los 10 minutos
- **THEN** el relé se acciona con un pulso largo

#### Scenario: Se apaga y se vuelve a encender
- **WHEN** tras el pulso corto el PC se detecta apagado y después vuelve a encenderse, a mano o por la propia Raspberry, antes de cumplirse los 10 minutos
- **THEN** no se envía el pulso largo

#### Scenario: El usuario actúa durante la espera
- **WHEN** durante la espera de forzado el usuario envía cualquier acción desde el panel
- **THEN** la espera de forzado se cancela y no se envía el pulso largo

### Requirement: Aviso del resultado del apagado programado
Con las notificaciones activas, el servicio SHALL enviar un único aviso al terminar un apagado programado indicando si el PC se apagó normalmente, si hubo que forzarlo o si sigue encendido tras el forzado, y SHALL NOT avisar de "acción sin efecto" por el pulso corto mientras dure la espera de forzado.

#### Scenario: Hubo que forzar
- **WHEN** el apagado programado terminó con un pulso largo y el PC se apagó
- **THEN** el móvil recibe un único aviso indicando que el apagado se forzó

#### Scenario: Espera larga sin aviso intermedio
- **WHEN** el pulso corto supera el tiempo máximo de transición pero la espera de forzado sigue en curso
- **THEN** no se envía el aviso de "acción sin efecto"

### Requirement: Cancelación del apagado programado
El panel SHALL permitir cancelar el apagado programado pendiente y, mientras esté en curso, la espera de forzado.

#### Scenario: Cancelar antes de la hora
- **WHEN** el usuario cancela el apagado programado antes de su hora
- **THEN** el relé no se acciona a esa hora y el panel deja de mostrarlo

### Requirement: Persistencia y horas vencidas del apagado programado
El apagado programado pendiente SHALL sobrevivir a un reinicio del servicio; una programación cuya hora pasó hace más de 5 minutos mientras el servicio no estaba en ejecución SHALL descartarse sin accionar el relé. Las horas SHALL interpretarse en la zona horaria configurada para el servicio.

#### Scenario: Reinicio antes de la hora
- **WHEN** la Raspberry se reinicia una hora antes de la hora programada
- **THEN** el apagado se ejecuta a su hora

#### Scenario: Raspberry apagada durante la hora programada
- **WHEN** el servicio arranca 2 horas después de la hora programada
- **THEN** la programación se descarta y el relé no se acciona
