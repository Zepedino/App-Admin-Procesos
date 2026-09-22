# ADR 0005 — SQLite en desarrollo, Postgres (Supabase) en producción

**Fecha:** 2026-09-07 · **Estado:** aceptado

## Contexto

El PRD indica PostgreSQL. El despliegue previsto usa la capa gratuita de
Supabase con la aplicación en Render. En desarrollo, exigir Postgres obliga a
levantar un contenedor para cualquier prueba.

## Decisión

Una sola capa SQLAlchemy, con el motor determinado por `DATABASE_URL`:

- Desarrollo y tests: SQLite.
- Producción: Postgres de Supabase.

La configuración normaliza las URL `postgres://` y `postgresql://` que entregan
Supabase y Render, fijando el driver psycopg 3. En SQLite se activan
`foreign_keys=ON` (las claves foráneas no son opcionales) y `journal_mode=WAL`
(lectura concurrente mientras corren los jobs).

Regla: **ningún SQL específico de motor fuera de `nucleo/db.py`**.

## Consecuencias

- Se puede clonar el repositorio y tener el sistema corriendo sin instalar nada.
- Riesgo asumido: una diferencia de comportamiento entre motores podría pasar
  los tests y fallar en producción. Ya ocurrió una vez —SQLite devolvía fechas
  sin zona horaria, y el detector de cambios reportaba adendas inexistentes— y
  se resolvió en la raíz con el tipo `FechaHoraUTC`, que fuerza UTC consciente
  de zona en ambos motores. Ese caso está cubierto por tests.
- Antes del primer despliegue hace falta Alembic para versionar el esquema; hoy
  las tablas se crean con `python -m backend.consola init-db`.
