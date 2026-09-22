# Estado real de construcción

**Actualizado:** 2026-09-08 · **Versión:** 0.1.0

Este documento dice qué está construido **de verdad**, qué es esqueleto y qué no
existe. Mantenerlo honesto es obligatorio: es lo que evita prometer lo que no está.
La misma información, generada desde el código, está en `/sistema/modulos`.

---

## Verificado contra datos reales

No hay datos de ejemplo inventados en ninguna parte del sistema.

| Qué se verificó | Resultado |
|---|---|
| Listado por fecha de la API | 1.214 licitaciones reales del 04-09-2026 y 1.162 del 03-09-2026 |
| Detalle por código | 3 licitaciones reales completas, guardadas como fixtures |
| Campos que entrega el listado | **Solo 4**: `CodigoExterno`, `Nombre`, `CodigoEstado`, `FechaCierre` |
| Filtro del perfil sobre datos reales | 1.214 → 3 candidatas; 1.162 → 1 candidata |
| Contador de cuota | 3 llamadas contadas y persistidas correctamente |
| Caché | 3 entradas, con TTL según estado |
| Reintentos y backoff | Probados de verdad: la API devolvió HTTP 429 y el sistema reintentó 3 veces y falló de forma visible |
| Encoding de la API | UTF-8 declarado y real (verificado a nivel de bytes) |
| Auditoría | Registra acciones de negocio y cambios de columna, con actor e identificador |
| Tests | 79, todos en verde; `ruff` sin hallazgos |

**Hallazgo real durante la verificación:** buscar la subcadena `"ito "` en el
listado real marca como candidata a *"Suministro señaléticas de Tránsito 2026"*,
porque `"transito "` contiene `"ito "`. Por eso el filtro usa límites de palabra
y hay un test que lo fija (`test_ito_no_calza_dentro_de_transito`).

---

## Por módulo

| Módulo | Fase | Estado | Qué hay |
|---|---|---|---|
| **M0 Procesos** | 0 | **parcial** | Procedimientos versionados: cada módulo trae su `PROCESO.md` junto al código y `sgl importar-procedimientos` los publica en `/procesos/`, guardando la versión anterior (RF-0.4). Estados del ciclo de vida con responsable y SLA. Revisión semanal con registro de ejecución, que cuenta pendientes vencidos de todo el sistema vía el registro del núcleo. Falta el editor en la UI y el seguimiento de cambios normativos. |
| **M1 Radar** | 1 | **parcial** | Sincronización por día, perfil de interés configurable desde la UI, filtro en dos pasadas, deduplicación, detección de cambios con diff, descarte tipificado, bandeja del día, lista negra de organismos, 3 jobs programados. Falta geocodificación para el criterio de distancia y el enganche con M2. |
| M2 Fichas y anexos | 1 | planificado | Bloqueado: hay que revisar los términos de uso del portal y fijar el correo de contacto del scraper (RF-2.3). |
| M3 Análisis IA y scoring | 2 | planificado | Bloqueado por la pregunta abierta 5: sin los criterios reales de Daniela no se puede programar el scoring. La capa `LLMProvider` y sus guardas ya existen y están testeadas. |
| M4 Pipeline y calendario | 1 | planificado | Los datos de fechas ya se guardan; falta la vista. |
| M5 Adjudicación y puesta en marcha | 3 | planificado | Bloqueado por la pregunta abierta 8. |
| M6 Pagos y caja | 3 | planificado | Bloqueado por la pregunta abierta 4 (SERVIU vs. Servicio de Salud). |
| M7 Multas | 3 | planificado | — |
| M8 Terreno y horas | 4 | planificado | **Restricción legal**: v1 es control de gestión, no registro de asistencia. Verificar Ley 21.719 antes de construir. |
| M9 Reportes y Excel | 3 | planificado | — |
| M10 Notificaciones | 1 | planificado | La capa de proveedores (`providers/notify`) ya existe. Falta el módulo de negocio con preferencias por usuario. |
| M11 Documental y firma | 3 | planificado | El almacenamiento versionado por hash ya existe y está testeado. |

---

## Infraestructura transversal, construida y probada

| Pieza | Dónde | Qué garantiza |
|---|---|---|
| `ProcurementProvider` | `providers/procurement/` | Toda llamada a la API pasa por aquí, con caché, reintentos con backoff, contador de cuota y degradación al 80 %. Un test de arquitectura impide que aparezca una URL de la API fuera de esta capa. |
| Contador de cuota | `providers/procurement/cuota.py` | Persistido en base de datos: un reinicio no regala cuota ya gastada. Avisa una sola vez al cruzar el umbral. |
| Caché con TTL por estado | `providers/procurement/cache.py` | Las publicadas se refrescan cada 4 h; las cerradas, cada 30 días. Sirve caché vencida si la API está caída. |
| `LLMProvider` + guardas | `providers/llm/` | Las cinco reglas duras del PRD §4.4 están implementadas, no documentadas: `analizar()` es concreto y `_analizar()` abstracto, para que una implementación nueva no pueda saltarse la verificación. |
| Almacenamiento por hash | `providers/storage/local.py` | Versionado SHA-256. Mismo contenido no crea versión; contenido distinto sí, que es la detección de adendas de RF-2.4. |
| Auditoría | `core/auditoria.py` | Automática vía listeners de SQLAlchemy: nadie puede olvidarse de auditar. Identifica la entidad por su clave natural. |
| Bus de eventos | `core/eventos.py` | Los módulos no se importan entre sí. Catálogo cerrado de nombres, con test que lo verifica. |
| RBAC | `core/seguridad.py` | Matriz de permisos que traduce literalmente la tabla del PRD §3. |
| `FechaHoraUTC` | `core/modelo_base.py` | Todo instante entra y sale como UTC con zona. Sin esto, SQLite devolvía fechas sin zona y el detector de cambios reportaba adendas inexistentes. |
| Planificador | `core/planificador.py` | Ningún job puede registrarse sin manejo de error; un fallo emite evento y queda en `/sistema/jobs`. |
| Registro de módulos | `core/registro.py` | El sistema se arma leyendo la lista de módulos. Agregar uno no toca `main.py`. |
| Registro de pendientes | `core/pendientes.py` | Punto de extensión para que la revisión de los viernes cuente pendientes de módulos que aún no existen. |

---

## Lo que falta para operar en producción

1. **Ticket de Mercado Público** (Clave Única, demora). Sin él, el sistema opera
   con respuestas reales guardadas y lo advierte en cada pantalla.
2. **Ajustar el perfil de interés con Daniela.** El que se carga como semilla
   viene de los ejemplos textuales del PRD y está marcado como borrador.
3. **Autenticación.** Hoy todas las acciones quedan registradas como `sistema`.
   La matriz de permisos existe; falta el login que la active.
4. **Migraciones Alembic.** Hoy las tablas se crean con `init-db`. Para producción
   hace falta el versionado del esquema.
5. **Revisar los términos de uso del portal** antes de activar el scraper de M2.
