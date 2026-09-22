# CLAUDE.md — Sistema Único de Gestión de Licitaciones y Contratos (Consultora ITO / SERVIU)

Fuente de verdad funcional: [`documentos/PRD-v1-sistema-licitaciones.md`](documentos/PRD-v1-sistema-licitaciones.md).
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
(`backend/conectores/mercado_publico/`) con caché, reintentos con backoff y contador de cuota.
Al **80 % del tope diario el sistema degrada** (solo refresca lo que cierra en <48 h) y avisa al admin.
Nadie llama a `httpx` contra la API fuera de esa capa. Si ves una URL de mercadopublico.cl
fuera de `backend/conectores/mercado_publico/`, es un bug — y hay un test que lo detecta.

## 2. Reglas duras de IA (PRD §4.4)

1. Solo van al LLM **documentos públicos** (bases, anexos, resoluciones del portal).
   **Nunca** datos de trabajadores, remuneraciones ni documentos internos con nombres.
2. La IA **resume y pre-clasifica, no decide**.
3. Todo output de IA se muestra **marcado como tal**, con enlace al documento y página de origen.
   **Ningún monto o fecha generado por el modelo se muestra sin el dato original al lado.**
4. Capa `LLMProvider` abstracta (`backend/conectores/ia/`): cambiar de proveedor o pasar a
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

---

## 5. Estructura

```
iniciar.py            ← ejecutar esto levanta la aplicación. Solo stdlib, a propósito.
backend/              todo lo que hace
  app.py              fábrica de la aplicación
  consola.py          comandos de operación y diagnóstico
  plantillas.py       motor Jinja y filtros de presentación
  nucleo/             config, BD, auditoría, eventos, RBAC, planificador, registro
  conectores/         adaptadores al mundo externo, intercambiables por contrato
    mercado_publico/  API de ChileCompra (+ proveedor de fixtures)
    ia/               LLM, con las reglas duras del §2 implementadas
    archivos/         almacenamiento versionado por hash
    avisos/           correo, WhatsApp, consola
  modulos/            un paquete por módulo del PRD (m0_procesos … m11_documental)
frontend/             todo lo que se ve
  plantillas/         HTML Jinja (base/ y paginas/)
  estaticos/          CSS propio, sin build ni CDN
pruebas/              tests, incluidos los de arquitectura
documentos/           PRD, estado real, arquitectura, decisiones (ADR)
datos/                base de datos y archivos descargados (no se versiona)
```

**Reglas de dependencia (se testean, ver `pruebas/test_arquitectura.py`):**
- `nucleo/` no importa `modulos/` ni `conectores/`.
- `modulos/` no importa otro `modulos/`: se comunican por el **bus de eventos**
  (`nucleo/eventos.py`) o por el registro de extensión (`nucleo/pendientes.py`).
- `conectores/` no importa `modulos/`.

**Anatomía de un módulo** (todos idénticos, para que sea auditable y reparable):
```
modulos/mN_nombre/
  __init__.py   MANIFIESTO: id, nombre, RF que cubre, fase, estado, router, jobs
  models.py     tablas SQLAlchemy propias del módulo
  services.py   lógica de negocio (testeable sin HTTP)
  filtro.py     lógica pura, sin BD ni red (cuando hay reglas complejas)
  jobs.py       tareas programadas + registrar_jobs() + registrar_suscripciones()
  routes.py     endpoints y vistas
  PROCESO.md    M0: el procedimiento escrito de este flujo, versionado (RF-0.1)
```
Agregar un módulo = crear el paquete y añadirlo a `_MANIFIESTOS` en `backend/modulos/__init__.py`.
Nada más. **Si tuviste que tocar `nucleo/` o `app.py` para agregar un módulo, el diseño falló.**

---

## 6. Comandos

```bash
python iniciar.py                                 # levanta todo (instala si hace falta)
python -m backend.consola doctor                  # entorno, cuota, conectividad
python -m backend.consola sync-dia 2026-09-04     # trae un día desde la API real
python -m backend.consola importar-procedimientos # publica los PROCESO.md en la app
pytest                                            # tests, incluidos los de arquitectura
```

`iniciar.py` es el camino para quien no usa terminal. Los comandos de `consola`
son para operar y diagnosticar.

## 7. Estado actual

Ver [`documentos/ESTADO.md`](documentos/ESTADO.md) — qué está construido de verdad,
qué es esqueleto y qué no existe. Mantenerlo actualizado es obligatorio: es el
documento que evita prometer lo que no está.
