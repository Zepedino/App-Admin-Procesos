# ADR 0001 — Registro de decisiones

**Fecha:** 2026-09-07 · **Estado:** aceptado

## Contexto

El PRD pide que el sistema sea auditable y que se actualice cuando la realidad
contradiga un supuesto. Para eso hay que saber qué se decidió, cuándo y por qué;
si no, cada cambio futuro reabre discusiones ya cerradas.

## Decisión

Cada decisión de arquitectura o de producto que no sea obvia se registra aquí,
numerada, con contexto, decisión y consecuencias. Una decisión revertida no se
borra: se marca como sustituida por el ADR que la reemplaza.

## Consecuencias

- Un ADR más que escribir cuando se toma una decisión de peso.
- A cambio, dentro de seis meses se puede responder "por qué esto es así" sin
  depender de la memoria de nadie, que es exactamente el hallazgo 1 del
  levantamiento aplicado a nosotros mismos.
