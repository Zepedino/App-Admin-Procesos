# Procedimiento — M1 Radar de oportunidades

**Version:** 1.0 · **Responsable:** Encargado de licitaciones · **Ultima revision:** 2026-09-07

Documento exigido por RF-0.1: cada flujo del sistema tiene un procedimiento escrito,
versionado y accesible desde la pantalla correspondiente.

## Objetivo

Que ninguna licitacion que nos interesa pase sin ser vista, y que cada descarte
quede registrado con un motivo que sirva para mejorar los criterios.

## Entradas

- API de Mercado Publico (`licitaciones.json`), via `ProcurementProvider`.
- Perfiles de interes configurados en `/radar/perfiles`.
- Lista negra de organismos en `/radar/organismos`.

## Flujo automatico

| Paso | Cuando | Responsable | SLA |
|---|---|---|---|
| Sincronizacion nocturna | 23:15 diario (ventana 22:00-07:00) | Sistema | — |
| Refresco de cierres < 72h | cada 4 horas | Sistema | — |
| Aviso de cierres < 48h | 08:00 diario | Sistema | — |
| Revision de la bandeja del dia | dia habil | Encargado de licitaciones | mismo dia |
| Decision go/no-go | antes del 50% del plazo al cierre | Gerencia | 2 dias habiles |

## Flujo manual

1. Abrir `/radar/` (bandeja del dia) cada manana.
2. Revisar **Nuevas**: para cada una, marcar *Interesa* o *Descartar con motivo*.
   El motivo es obligatorio y tipificado (RF-1.5).
3. Revisar **Cambios detectados**: los criticos (fecha de cierre, monto, estado)
   van primero. Cerrar cada alerta con "visto" (RF-10.4).
4. Revisar **Cierran pronto**: confirmar que las que interesan tienen responsable.

## Como se decide que se pide a la API

El listado por fecha entrega solo cuatro campos por licitacion. Pedir el detalle
de todas costaria mas de mil llamadas de las 10.000 diarias. Por eso:

1. Se filtra por nombre contra las palabras clave del perfil (gratis).
2. Solo las candidatas gastan una llamada de detalle.
3. Lo ya descartado o cerrado no se vuelve a pedir.
4. Sobre el 80% de la cuota, solo se refresca lo que cierra en menos de 48 horas.

## Que hacer si falla

| Sintoma | Causa probable | Accion |
|---|---|---|
| "no hay perfiles de interes activos" | nadie configuro el perfil | crear uno en `/radar/perfiles` |
| Cuota agotada | carga historica sin limite | esperar al dia siguiente; usar `--limite` |
| "respuesta no reconocida" | la API cambio de formato | revisar `providers/procurement/`, avisar |
| Dias sin sincronizar | el job no corrio | `sgl sync-dia AAAA-MM-DD` y revisar el planificador |

## Bitacora de cambios

| Version | Fecha | Cambio |
|---|---|---|
| 1.0 | 2026-09-07 | Version inicial |
