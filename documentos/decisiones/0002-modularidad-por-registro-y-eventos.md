# ADR 0002 — Modularidad por registro de módulos y bus de eventos

**Fecha:** 2026-09-07 · **Estado:** aceptado

## Contexto

El PRD define doce módulos (M0–M11) que se construyen en cuatro fases a lo largo
de meses. Se pidió explícitamente que el sistema fuera modular, escalable,
auditable y reparable ante nuevos requerimientos.

El riesgo real no es el volumen de datos —son 3 a 10 usuarios—, sino el
**acoplamiento**: que construir M5 obligue a modificar M1, o que un fallo en M7
tumbe M3. En un sistema que se construye por fases durante meses, eso es lo que
lo vuelve imposible de mantener.

## Decisión

Tres mecanismos, los tres verificados por tests:

1. **Registro de módulos.** Cada módulo publica un manifiesto con su id, los RF
   que cubre, su fase, su estado real y lo que expone. La aplicación se arma
   leyendo esa lista. Agregar un módulo es crear el paquete y añadirlo a
   `_MANIFIESTOS`; no se toca `app.py` ni `nucleo/`.

2. **Bus de eventos síncrono.** Los módulos no se importan entre sí. M1 emite
   `licitacion.marcada_interesa` sin saber que existe M2. Los nombres de evento
   viven en un catálogo cerrado, porque un emisor y un suscriptor que difieren
   por un error de tipeo fallan en silencio.

3. **Registros de extensión.** Cuando un módulo necesita agregar información al
   conjunto —los pendientes vencidos de la revisión de los viernes—, se inscribe
   en un registro del núcleo, en vez de que el núcleo lo consulte.

Se descartó una cola de mensajes (Celery, RQ): con este volumen sería
infraestructura sin beneficio. La interfaz del bus permite cambiarlo después sin
tocar a los emisores.

## Consecuencias

- Construir M2, M5 o M7 no requiere modificar los módulos ya en producción.
- Un módulo puede quitarse o quedar sin construir sin romper el arranque.
- Los tests de arquitectura fallan si alguien rompe una regla de dependencia,
  que es la única forma de que las reglas sobrevivan al paso del tiempo.
- El bus síncrono significa que un manejador lento retrasa al emisor. Con este
  volumen es irrelevante; si deja de serlo, se cambia la implementación del bus.
