# ADR 0004 — Frontend server-rendered, CSS propio, sin build

**Fecha:** 2026-09-07 · **Estado:** aceptado

## Contexto

El PRD deja abierta la elección: "React + Tailwind, o server-rendered si
prefieres menos piezas". Son 3 a 10 usuarios internos. El criterio explícito del
proyecto es que sea auditable, reparable y desplegable como una sola pieza, sin
perder calidad visual.

## Decisión

FastAPI + Jinja2, con un único archivo CSS escrito a mano, sin dependencias de
CDN ni cadena de build.

Se descartó Tailwind por CDN (dependencia de red en tiempo de ejecución y aviso
explícito de no usarlo en producción) y Tailwind compilado (introduce Node y un
paso de build en un proyecto que por lo demás es solo Python).

El CSS usa tokens en `:root` y los componentes solo consumen tokens; incluye
modo oscuro por `prefers-color-scheme` y es responsive.

## Consecuencias

- Un solo proceso que desplegar: sirve API y páginas.
- El CSS completo se lee de arriba abajo. Cambiar la paleta es cambiar un bloque.
- No hay estado de cliente que sincronizar, que es la mitad de los bugs de una SPA.
- Contrapartida: M8 (registro de visitas en terreno, offline-first) necesitará
  service worker y almacenamiento local. Es un añadido aislado a esa pantalla,
  no un cambio de enfoque, y la API JSON ya existe para alimentarlo.
