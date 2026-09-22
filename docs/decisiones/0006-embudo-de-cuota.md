# ADR 0006 — Embudo de dos pasadas para no agotar la cuota diaria

**Fecha:** 2026-09-07 · **Estado:** aceptado

## Contexto

Verificado contra la API real: la consulta por fecha devuelve **1.214
licitaciones** para un día hábil, pero solo cuatro campos por licitación
(`CodigoExterno`, `Nombre`, `CodigoEstado`, `FechaCierre`). El detalle completo
—donde están el organismo, el monto, las fechas del proceso y las categorías
UNSPSC— exige una llamada **por código**.

El tope es de 10.000 solicitudes diarias por ticket y no es modificable. Pedir
el detalle de todo lo del día costaría 1.215 llamadas: tres días agotarían el
ticket.

## Decisión

Filtrado en dos pasadas:

1. **Pasada barata (0 llamadas).** Se filtra por el nombre contra las palabras
   clave del perfil. Sobre datos reales: 1.214 a 3 candidatas.
2. **Pasada cara (1 llamada por candidata).** Solo las candidatas piden detalle,
   y se reevalúan con la información completa: categorías UNSPSC, región, monto
   y banderas.

Complementos: lo ya descartado o cerrado no vuelve a pedir detalle; en modo
degradado (80 % de la cuota) solo se refresca lo que cierra en menos de 48 horas;
la sincronización nocturna tiene un tope explícito de detalles por corrida.

El emparejamiento de palabras clave usa **límites de palabra**, no subcadenas.
Motivo concreto: buscar "ito " en el listado real marca como candidata a
"Suministro señaléticas de Tránsito 2026", porque "transito " contiene "ito ".
Un radar que entrega esa basura se deja de mirar en una semana.

## Consecuencias

- Un día hábil cuesta del orden de 4 llamadas en vez de 1.215.
- El filtro por nombre puede dejar pasar una licitación cuyo nombre no diga nada
  pero cuya descripción sí. Es una pérdida aceptada y medible: las candidatas que
  el detalle descarta se guardan igual, para poder afinar el perfil con datos.
- El resultado del filtro se guarda con la explicación de por qué entró. Si el
  encargado no puede ver por qué una licitación apareció en su bandeja, no
  confía en el radar.
