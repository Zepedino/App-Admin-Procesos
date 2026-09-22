# ADR 0003 — Proveedor de fixtures con respuestas reales, no datos inventados

**Fecha:** 2026-09-07 · **Estado:** aceptado

## Contexto

El ticket de la API de Mercado Público se solicita con Clave Única y demora; la
fase 0 del PRD lo pide precisamente porque bloquea. Pero detener el desarrollo
hasta que llegue significa perder semanas.

La salida habitual —generar datos de ejemplo— tiene un problema serio: se
programa contra una forma de datos imaginada, y cuando llega el dato real la
mitad de los supuestos son falsos. Peor aún, un dato inventado que se cuela a
una decisión de negocio es un daño real.

## Decisión

`ProveedorFixture` reproduce respuestas **literales** de la API, capturadas con
`sgl capturar-fixture` y guardadas en `tests/fixtures/api/`. No genera nada.

Cuando falta un fixture, **no adivina**: devuelve vacío y lo registra de forma
visible. Y toda pantalla del sistema muestra un aviso permanente de que los
datos no vienen de la API en vivo.

Antes de escribir el modelo de datos se capturaron y verificaron respuestas
reales, siguiendo el orden de trabajo del PRD sección 12.

## Consecuencias

- El modelo de datos se hizo contra la forma real de la API, no la documentada.
  Esto ya reveló que el listado por fecha entrega **solo cuatro campos**, que es
  lo que obliga al embudo de cuota de M1.
- Los tests son deterministas, no gastan cuota y no dependen de que el portal
  esté arriba.
- El día que llegue el ticket, se completa `MP_TICKET` en `.env` y no cambia una
  línea de lógica de negocio.
- Un bug de producción se puede reproducir capturando la respuesta que lo causó.
