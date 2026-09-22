# Procedimiento — M0 Procesos documentados

**Version:** 1.0 · **Responsable:** Jefe del area de Procesos · **Ultima revision:** 2026-09-07

## Objetivo

Que cada flujo del sistema tenga un procedimiento escrito, versionado y
accesible desde la pantalla donde se ejecuta (RF-0.1), y que la revision de los
viernes tenga alcance, responsable y registro (RF-0.3).

Aborda el hallazgo 1 del levantamiento: los procesos no estan documentados.
Varios de los otros hallazgos son sintomas de este.

## Como funciona

- Cada modulo trae su `PROCESO.md` junto al codigo, no en una carpeta aparte.
- `sgl importar-procedimientos` los carga a la base de datos y los deja visibles
  en `/procesos/`. Cada version anterior se conserva (RF-0.4).
- Cada estado del ciclo de vida tiene responsable y SLA en dias (RF-0.2),
  editables en la base y visibles en `/procesos/`.

## Revision semanal (RF-0.3)

| Paso | Responsable | Cuando |
|---|---|---|
| Abrir `/procesos/revision-semanal` | Jefe de area | viernes |
| Revisar pendientes vencidos de todo el sistema | Jefe de area | viernes |
| Revisar procedimientos con revision vencida | Jefe de area | viernes |
| Registrar ejecucion, observaciones y acuerdos | Jefe de area | viernes |

Los pendientes vencidos se cuentan desde el registro del nucleo: cada modulo
inscribe su propio contador, asi que la revision cubre mas terreno a medida que
se construyen M5, M6 y M7, sin modificar este procedimiento.

## Cuando actualizar un procedimiento

- Cuando cambia el flujo real.
- Cuando la revision del viernes detecta que lo escrito ya no se cumple.
- Al construir o modificar el modulo correspondiente. El PRD lo dice: cada
  modulo documenta su proceso al construirse.

Actualizar significa editar el `PROCESO.md` del modulo, subir la version y
volver a importar. La version anterior queda en la bitacora.

## Bitacora de cambios

| Version | Fecha | Cambio |
|---|---|---|
| 1.0 | 2026-09-07 | Version inicial |
