# Spec Delta

## Purpose

Permite accionar desde un panel móvil el pulsador de encendido del PC, cerrando momentáneamente el relé conectado a la Raspberry Pi, con la acción adecuada al estado del PC y salvaguardas contra accionamientos indebidos.

## ADDED Requirements

### Requirement: Acción de encendido con el PC apagado
Cuando el estado es "apagado", el panel SHALL ofrecer como acción principal "Encender", que cierra el relé con un pulso corto.

#### Scenario: Encender
- **WHEN** el estado es "apagado" y el usuario pulsa "Encender"
- **THEN** el relé se cierra durante la duración del pulso corto y se abre

#### Scenario: Acciones de apagado no visibles como principales
- **WHEN** el estado es "apagado"
- **THEN** el panel no muestra "Apagar" y muestra "Forzar apagado" solo como opción secundaria

### Requirement: Acciones de apagado con el PC encendido
Cuando el estado es "encendido", el panel SHALL ofrecer "Apagar" (pulso corto) y "Forzar apagado" (pulso largo), y SHALL NOT ofrecer "Encender".

#### Scenario: Apagar
- **WHEN** el estado es "encendido" y el usuario pulsa "Apagar"
- **THEN** el relé se cierra durante la duración del pulso corto y se abre

#### Scenario: Forzar apagado
- **WHEN** el estado es "encendido" y el usuario confirma "Forzar apagado"
- **THEN** el relé se cierra durante la duración del pulso largo y se abre

### Requirement: Confirmación del apagado forzado
El panel SHALL exigir una confirmación deliberada (mantener pulsado al menos 2 segundos) antes de enviar un apagado forzado, y un toque simple SHALL NOT accionarlo.

#### Scenario: Toque accidental
- **WHEN** el usuario toca brevemente "Forzar apagado"
- **THEN** el relé no se acciona y el panel indica que hay que mantener pulsado

#### Scenario: Pulsación mantenida
- **WHEN** el usuario mantiene pulsado "Forzar apagado" durante 2 segundos
- **THEN** se envía el apagado forzado

### Requirement: Apagado forzado de un PC que no responde a ping
Cuando el estado es "apagado", el panel SHALL ofrecer como opción secundaria, no destacada, el apagado forzado, para el caso de un PC colgado que ya no responde a ping.

#### Scenario: PC colgado
- **WHEN** el estado es "apagado", el usuario abre las opciones secundarias y confirma "Forzar apagado"
- **THEN** el relé se cierra durante la duración del pulso largo

### Requirement: Duraciones de pulso configurables y acotadas
Las duraciones del pulso corto (500 ms por defecto) y largo (6 s por defecto) SHALL ser configurables por entorno, y el servicio SHALL negarse a arrancar con una duración mayor de 10 segundos o un pulso corto de 2 segundos o más.

#### Scenario: Valores por defecto
- **WHEN** no se configuran duraciones
- **THEN** el pulso corto dura 500 ms y el largo 6 s

#### Scenario: Duración fuera de rango
- **WHEN** se configura un pulso largo de 30 segundos
- **THEN** el servicio termina al arrancar con un error en el registro del sistema

### Requirement: Un solo accionamiento a la vez
El servicio SHALL rechazar toda acción recibida mientras hay un pulso en curso o durante los 5 segundos siguientes a su fin, venga del mismo navegador o de otro, y el panel SHALL deshabilitar los botones durante ese intervalo.

#### Scenario: Doble toque
- **WHEN** el usuario pulsa "Encender" dos veces seguidas
- **THEN** el relé se acciona una sola vez

#### Scenario: Dos navegadores a la vez
- **WHEN** dos navegadores autorizados envían una acción con menos de un segundo de diferencia
- **THEN** solo se ejecuta la primera y el segundo recibe el aviso de que hay una acción en curso

### Requirement: La acción se valida contra el estado actual
El servicio SHALL rechazar "Encender" si el estado detectado es "encendido" y "Apagar" si es "apagado", de modo que un panel con información desfasada no provoque la acción contraria a la mostrada.

#### Scenario: Panel desfasado
- **WHEN** el panel muestra "Encender" pero el PC ya está encendido y el usuario pulsa
- **THEN** el relé no se acciona y el panel se actualiza al estado real

### Requirement: El relé nunca queda cerrado fuera de un pulso
El relé SHALL permanecer abierto al arrancar la Raspberry y el servicio, y SHALL quedar abierto si el servicio se detiene, falla o se reinicia durante un pulso. Arrancar o reiniciar el servicio SHALL NOT producir ningún pulso.

#### Scenario: Reinicio del servicio
- **WHEN** el servicio se reinicia con el PC encendido
- **THEN** el relé no se cierra en ningún momento y el PC sigue encendido

#### Scenario: Fallo durante un pulso largo
- **WHEN** el proceso del servicio muere a mitad de un pulso largo
- **THEN** el relé queda abierto

#### Scenario: Arranque de la Raspberry
- **WHEN** la Raspberry arranca tras un corte de energía
- **THEN** el relé no se cierra durante el arranque

### Requirement: Polaridad y pin del relé configurables
El pin GPIO del relé (23 por defecto) y su polaridad (activo en alto o en bajo) SHALL ser configurables por entorno, y el servicio SHALL negarse a arrancar si la polaridad no está definida explícitamente.

#### Scenario: Polaridad sin definir
- **WHEN** el servicio arranca sin polaridad configurada
- **THEN** termina con un error en el registro del sistema sin tocar el pin

#### Scenario: Módulo activo en bajo
- **WHEN** se configura polaridad activa en bajo
- **THEN** el pin permanece sin manejar (alta impedancia, relé abierto) en reposo y se lleva a bajo solo durante el pulso

### Requirement: Panel utilizable en móvil
El panel SHALL ser utilizable con una mano en una pantalla de 360 px de ancho sin desplazamiento horizontal ni zoom, con botones de acción de al menos 48 px de alto, y SHALL confirmar visualmente el resultado de cada acción.

#### Scenario: Pantalla de móvil
- **WHEN** se abre el panel en una pantalla de 360 px de ancho
- **THEN** el estado y las acciones se ven completos sin desplazamiento horizontal

#### Scenario: Confirmación de acción
- **WHEN** el servicio acepta una acción
- **THEN** el panel muestra que el pulso fue enviado y pasa al estado de transición
