# CLAUDE.md — Sistema Único de Gestión de Licitaciones y Contratos (Consultora ITO / SERVIU)

Fuente de verdad funcional: [`docs/PRD-v1-sistema-licitaciones.md`](docs/PRD-v1-sistema-licitaciones.md).
**Si la realidad contradice un supuesto del PRD, se actualiza el PRD en el mismo cambio.** Va a pasar.

---

## 1. Restricciones NO NEGOCIABLES — API Mercado Público (PRD §4.2)

1. **Ticket por persona**, solicitado con Clave Única. Nunca en el repositorio: solo `MP_TICKET` por entorno.
2. **10.000 solicitudes/día por ticket.** Tope duro, no modificable.
3. Validación por IP. Pueden restringir por volumen desde una misma IP.
4. **Cargas masivas solo entre 22:00 y 07:00** (hora de Chile).
5. Plataforma etiquetada como beta: **asumir interrupciones** siempre.
6. ChileCompra desarrolla un portal API unificado nuevo → el adaptador se reescribe, nada más.

**Implementación obligatoria:** toda llamada pasa por `ProcurementProvider`
(`src/sgl/providers/procurement/`) con caché, reintentos con backoff y contador de cuota.
Al **80 % del tope diario el sistema degrada** (solo refresca lo que cierra en <48 h) y avisa al admin.
Nadie llama a `httpx` contra la API fuera de esa capa. Si ves una URL de mercadopublico.cl
fuera de `providers/procurement/`, es un bug.

## 2. Reglas duras de IA (PRD §4.4)

1. Solo van al LLM **documentos públicos** (bases, anexos, resoluciones del portal).
   **Nunca** datos de trabajadores, remuneraciones ni documentos internos con nombres.
2. La IA **resume y pre-clasifica, no decide**.
3. Todo output de IA se muestra **marcado como tal**, con enlace al documento y página de origen.
   **Ningún monto o fecha generado por el modelo se muestra sin el dato original al lado.**
4. Capa `LLMProvider` abstracta (`src/sgl/providers/llm/`): cambiar de proveedor o pasar a
   tier pagado no toca la lógica de negocio.
5. Los campos extraídos son **editables** y cada corrección humana queda registrada.

## 3. Política de scraping (PRD RF-2.3)

- Solo la **ficha pública** de la licitación. **Nunca** la sesión autenticada del proveedor.
- Cola **secuencial** con delay entre requests. **Sin paralelismo.**
- User-agent identificable, con correo de contacto.
- Respetar `robots.txt`. Revisar términos de uso del portal antes de activar.
- Máximo N licitaciones por día (configurable, valor inicial bajo).
- Reintentos con backoff; tras 3 fallos, alerta al usuario para descarga manual.
- **Fallar visiblemente.** Un scraper que se rompe en silencio es peor que no tenerlo.

## 4. Reglas transversales

- **Ningún job falla en silencio.** Reintenta y **avisa** (PRD §6).
- **Auditoría** de quién cambió qué, con énfasis en montos y multas.
- **Acceso por rol** (PRD §3). Costos de personal y rentabilidad: solo Gerencia.
- Secretos fuera del repositorio, siempre por variable de entorno.
- **Todo exportable a Excel/CSV.** Excel deja de ser fuente de verdad pero sigue siendo salida válida.
- Datos personales: minimizar, definir retención, **no enviar personas a APIs de terceros**
  (Ley 21.719 pendiente de verificar antes de construir M8).

## 5. Arquitectura — cómo se agrega algo sin romper nada

```
src/sgl/
  core/        núcleo. NO importa nada de modules/. Config, DB, auditoría, eventos, RBAC, scheduler.
  providers/   adaptadores a mundo externo. Intercambiables por contrato (ABC).
  modules/     un paquete por módulo del PRD (m0_procesos … m11_documental).
  web/         plantillas Jinja + estáticos. Server-rendered, un solo desplegable.
```

**Reglas de dependencia (se testean, ver `tests/test_arquitectura.py`):**
- `core/` no importa `modules/` ni `providers/`.
- `modules/` no importa otro `modules/` directamente: se comunican por el **bus de eventos**
  (`core/events.py`) o por servicios expuestos en el `__init__.py` del módulo.
- `providers/` no importa `modules/`.

**Anatomía de un módulo** (todos idénticos, para que sea auditable y reparable):
```
modules/mN_nombre/
  __init__.py   MANIFIESTO: id, nombre, RF que cubre, fase, dependencias, router, jobs
  models.py     tablas SQLAlchemy propias del módulo
  schemas.py    pydantic de entrada/salida
  services.py   lógica de negocio pura (testeable sin HTTP ni DB real)
  jobs.py       tareas programadas, registradas por el scheduler
  routes.py     endpoints FastAPI + vistas Jinja
  PROCESO.md    M0: el procedimiento escrito de este flujo, versionado (RF-0.1)
```
Agregar un módulo = crear el paquete y añadirlo a `MODULOS` en `src/sgl/modules/__init__.py`.
Nada más. Si tuviste que tocar `core/` para agregar un módulo, el diseño falló.

## 6. Comandos

```bash
python -m sgl.cli doctor              # verifica entorno, cuota, conectividad
python -m sgl.cli sync-dia 04092026   # trae un día crudo desde la API real
python -m sgl.cli serve               # levanta la app
pytest                                 # tests, incluidos los de arquitectura
```

## 7. Estado actual

Ver [`docs/ESTADO.md`](docs/ESTADO.md) — qué está construido de verdad, qué es stub y qué no existe.
Mantenerlo actualizado es obligatorio: es el documento que evita prometer lo que no está.
