# PRD v1.0 — Sistema Único de Gestión de Licitaciones y Contratos
### Consultora ITO / SERVIU

**Estado:** aprobado para implementación
**Fecha:** septiembre 2026
**Reemplaza:** borrador 0.1

---

## 1. Principio rector: una sola app

Todo el ciclo de vida vive en el mismo sistema, con la misma base de datos y el mismo repositorio de archivos. No hay planilla paralela, no hay carpeta suelta en el escritorio, no hay información que solo esté en la cabeza de alguien.

**Ciclo de vida completo:**

```
Detección → Evaluación → Decisión (go/no-go) → Preparación de oferta → Ofertada
    → Adjudicada → Puesta en marcha → Ejecución → Estados de pago → Cierre
                        ↕                              ↕
                    Multas                        Asistencia / horas
                        ↕                              ↕
                          Flujo de caja y rentabilidad
```

Una licitación entra por el radar y sale, meses después, como un contrato cerrado con su rentabilidad real calculada. **Es la misma entidad todo el rato**, no se re-digita en ningún punto.

### Qué reemplaza este sistema

| Hoy | Después |
|---|---|
| Búsqueda manual en el portal | M1 (radar automático) |
| Correos de Mercado Público en una bandeja | M10 (ingesta y conversión a eventos) |
| Descarga manual de bases y anexos | M2 (scraper) |
| "¿Qué documentos pedían?" leído a mano | M3 (extracción IA) |
| Decisión de postular por criterio informal | M3 (scoring explícito) |
| Fechas en la cabeza o en un Excel | M4 (calendario único) |
| "Ganamos, ¿y ahora qué?" | **M5 (puesta en marcha)** |
| Excel de estados de pago | M6 |
| Multas sin registro | M7 |
| Asistencia y horas en papel | M8 |

**Regla de convivencia con Excel:** el sistema importa las planillas actuales y exporta a los formatos que ya usan para reportar. Excel deja de ser la fuente de verdad, pero sigue siendo una salida válida. Si peleas contra Excel, pierdes.

---

## 2. Contexto

Empresa de inspección técnica de obra y acompañamiento a obra para construcción de viviendas, principalmente para el SERVIU. Procesos de soporte: licitación por Mercado Público, contratación, pago, firma electrónica avanzada.

Del levantamiento salieron ocho hallazgos, la mayoría síntomas del primero (procesos no documentados). El sistema los aborda así:

| # | Hallazgo | Módulo |
|---|---|---|
| 1 | Procesos no documentados | M0 + diseño transversal |
| 2 | Notificaciones de Mercado Público sin seguimiento | M1, M2, M10 |
| 3 | Revisión de manual los viernes sin alcance claro | M0 |
| 4 | Sin criterios para distinguir tipos de licitación | M1, M3 |
| 5 | Lejanía geográfica | M3 (costo de traslado), M8 (agrupación de visitas) |
| 6 | Dotación insuficiente | M4 (simulador de capacidad) |
| 7 | Flujo de caja / pago a 90 días | M6 |
| 8 | Municipalidades excluidas | M1 (lista negra con motivo) |
| — | Multas | M7 |

---

## 3. Usuarios y roles

| Rol | Permisos |
|---|---|
| **Gerencia (Daniela)** | Todo. Aprueba go/no-go. Único que ve costos de personal y rentabilidad. |
| **Encargado de licitaciones** | Radar, fichas, checklist, pipeline, calendario. No ve remuneraciones. |
| **Jefe de proyecto / ITO** | Sus contratos, visitas, informes, horas, checklist preventivo de multas. |
| **Administración y finanzas** | Contratos, estados de pago, garantías, cobranza, multas. |
| **Admin** | Configuración, usuarios, integraciones, cuotas. |

3 a 10 usuarios. No se necesita arquitectura de escala; sí control de acceso por rol, porque hay datos de multas y remuneraciones.

---

## 4. Restricciones técnicas (obligatorio leer antes de implementar)

### 4.1 API de Mercado Público — lo que entrega

Base: `https://api.mercadopublico.cl/servicios/v1/publico/`

- **`licitaciones.json`** — por `codigo` (detalle completo), por `fecha` (ddmmaaaa, datos básicos), por `estado`, por `CodigoOrganismo`, por `CodigoProveedor`.
- **`ordenesdecompra.json`** — mismas variantes.
- **`Empresas/BuscarProveedor?rutempresaproveedor=`** — RUT con puntos, guion y DV.
- **`Empresas/BuscarComprador`** — listado de organismos.
- API de **Compra Ágil** documentada aparte.

Estados de licitación: Publicada=5, Cerrada=6, Desierta=7, Adjudicada=8, Revocada=18, Suspendida=19.

Tipos relevantes: **LS** (servicios personales especializados, probablemente el principal), LE (100–1000 UTM), LP (>1000 UTM), L1 (<100 UTM).

Campos clave para el scoring: monto estimado y su naturaleza (1=presupuesto disponible, 2=precio referencial), modalidad de pago, `Obras`, `TomaRazon`, `SubContratacion`, `ExtensionPlazo`, `EsRenovable`, `VisibilidadMonto`, fechas de consultas / cierre / apertura / adjudicación.

### 4.2 Límites operativos — respetarlos es requisito, no sugerencia

- Ticket por persona, se solicita con Clave Única y llega por correo.
- **10.000 solicitudes/día por ticket**, tope no modificable.
- Validación por IP; pueden restringir según volumen desde una misma IP.
- Cargas masivas recomendadas **entre 22:00 y 07:00**.
- La plataforma ha estado etiquetada como beta; asumir interrupciones.
- ChileCompra está desarrollando un **portal API unificado nuevo** que reemplazará progresivamente el actual.

**RNF crítico:** toda llamada pasa por una capa `ProcurementProvider` con caché, reintentos con backoff y contador de cuota. Cuando salga la API nueva se reescribe el adaptador y nada más. Si el contador llega al 80% del tope diario, el sistema degrada (solo refresca lo que cierra en <48h) y avisa al admin.

### 4.3 Lo que la API no entrega

| Necesidad | Solución en este PRD |
|---|---|
| Bases y anexos | **M2 — scraper** |
| Notificaciones de la cuenta privada | **M10 — ingesta de correo** |
| Multas aplicadas | **M7 — registro manual + IA sobre la resolución** |
| Pago efectivamente recibido | **M6 — conciliación manual** |
| Contratos fuera del portal | **M5 — ingreso manual** |

### 4.4 IA (Gemini free tier)

- Free tier hoy es solo modelos **Flash**, del orden de 10–15 RPM y unos cientos a ~1.500 requests/día. Los Pro pasaron a pago durante 2026.
- **Google puede usar los datos del tier gratuito para entrenar.**

**Reglas duras:**
1. Solo van al LLM **documentos públicos** (bases, anexos, resoluciones publicadas en el portal). Nunca datos de trabajadores, remuneraciones, ni documentos internos con nombres.
2. La IA **resume y pre-clasifica, no decide**.
3. Todo output de IA se muestra marcado como tal, con enlace al documento y página de origen. **Ningún monto o fecha generado por el modelo se muestra sin el dato original al lado.**
4. Capa `LLMProvider` abstracta, para cambiar de proveedor o pasar a tier pagado sin tocar la lógica.
5. Los campos extraídos son editables; cada corrección humana queda registrada (sirve para medir la precisión del modelo con el tiempo).

---

## 5. Módulos

### M0 — Procesos documentados *(transversal, desde el día 1)*

- **RF-0.1** Cada flujo del sistema tiene un procedimiento escrito, versionado, accesible desde la pantalla correspondiente.
- **RF-0.2** Cada estado del ciclo de vida tiene responsable y SLA en días.
- **RF-0.3** La "revisión de los viernes" se convierte en una vista del sistema: pendientes vencidos, cambios normativos por revisar, procedimientos sin revisión hace más de X meses. Con responsable y registro de ejecución.
- **RF-0.4** Bitácora de cambios de procedimiento.

---

### M1 — Radar de oportunidades

- **RF-1.1** Job nocturno (22:00–07:00) que sincroniza licitaciones publicadas. Pull liviano cada 4h para las que cierran en menos de 72h.
- **RF-1.2** **Perfil de interés configurable desde la UI** — nada hardcodeado:
  - Palabras clave e exclusiones (ej. incluir "inspección técnica", "ITO", "asesoría a la inspección", "supervisión de obras"; excluir "suministro", "arriendo", "provisión de")
  - Categorías ONU (UNSPSC), regiones y comunas
  - Rango de monto, tipo de licitación, flag `Obras`
  - **Lista negra de organismos** con motivo registrado (hallazgo 8)
  - Lista blanca (SERVIU por región)
- **RF-1.3** Deduplicación: lo ya visto o descartado no reaparece como nuevo.
- **RF-1.2bis — Vigilancia dirigida por organismo.** *(agregado tras verificar con
  datos reales, octubre 2026)*
  El listado diario de la API **no incluye el organismo comprador**, así que el
  filtro por palabras clave es lo único disponible en la pasada barata. Medido
  sobre 8.132 licitaciones de 7 días hábiles: el radar capturó **cero** del
  SERVIU. No por ausencia, sino porque el SERVIU las titula *"Fiscalización
  Técnica de Obras" (FTO)* y el perfil buscaba *"inspección técnica"*; se
  perdieron 11 del rubro exacto, varias de los programas DS49 y DS27.
  Además, el SERVIU publica licitaciones llamadas solo `LP 110-2026`, sin
  ninguna palabra útil en el título: ningún perfil las encontraría.
  **Por eso:** los organismos marcados como vigilados se consultan por su
  código (`CodigoOrganismo` + `estado=activas`), lo que devuelve todo lo que
  tengan abierto. Trece SERVIU son trece llamadas de las 10.000 diarias.
  El perfil se sigue evaluando sobre ellas, pero **para ordenar, no para
  filtrar**: de un organismo vigilado se revisa todo.
- **RF-1.4** **Detección de cambios / adendas.** Si cambia la fecha de cierre, se publica una aclaración o se modifica el monto, se genera alerta con el *diff*. Si hay anexos nuevos, se dispara re-scraping (ver M2).
- **RF-1.5** Descarte con motivo tipificado obligatorio. En 6 meses estos datos dicen si los criterios sirven.
- **RF-1.6** Vista "bandeja del día": lo nuevo, lo que cambió, lo que cierra pronto.

---

### M2 — Ficha consolidada y descarga automática de anexos *(scraper)*

Este es el módulo que más tiempo ahorra. La API no trae los archivos; hay que ir a buscarlos.

- **RF-2.1** Ficha consolidada: datos de la API + cronograma + anexos + análisis IA + historial de cambios, todo en una pantalla.
- **RF-2.2 — Scraper de anexos.** Cuando una licitación se marca como **"interesa"** (manual) o supera el umbral de scoring (automático), se encola la descarga de **todos** los archivos de la ficha pública: bases administrativas, bases técnicas, anexos, planos, formularios, aclaraciones.
- **RF-2.3** Política del scraper (requisito, no recomendación):
  - Solo la **ficha pública** de la licitación. Nunca la sesión autenticada del proveedor.
  - Cola secuencial con delay entre requests. Sin paralelismo.
  - User-agent identificable, con correo de contacto.
  - Respetar `robots.txt`. Revisar términos de uso del portal antes de activar.
  - Máximo N licitaciones por día (configurable, valor inicial bajo).
  - Reintentos con backoff; si falla 3 veces, alerta al usuario para descarga manual.
  - **Fallar visiblemente.** Un scraper que se rompe en silencio es peor que no tenerlo.
- **RF-2.4** Almacenamiento: `/licitaciones/{codigo}/anexos/`, hash SHA-256 por archivo para deduplicar y detectar cambios. Si un anexo cambia de hash, se guarda como **nueva versión** y se alerta — es exactamente el caso de una adenda que modifica las bases.
- **RF-2.5** Extracción de texto de PDF, con fallback a OCR para bases escaneadas (existen y son frecuentes).
- **RF-2.6 — Checklist documental.** Desde las bases se extrae la lista de documentos exigidos: anexos administrativos, técnicos y económicos, formato, si requiere firma electrónica avanzada, si va en papel o portal.
- **RF-2.7 — Biblioteca de documentos de la empresa** con vencimientos: F30, F30-1, inscripción en Registro de Proveedores, boletas de garantía, seguros, patente, certificados de título del equipo, declaraciones juradas. Alerta anticipada de vencimiento.
- **RF-2.8 — Matching automático:** para cada documento exigido, el sistema propone el de la biblioteca que corresponde y marca en rojo lo que falta o está vencido.
- **RF-2.9** Seguimiento del foro: fecha límite para consultar, preguntas enviadas, fecha de publicación de respuestas, alerta cuando salen (y re-scraping de la ficha ese día).

---

### M3 — Análisis IA y scoring go/no-go

- **RF-3.1** Resumen automático en formato fijo: objeto, plazo, monto y naturaleza, garantías exigidas, forma de pago, criterios de evaluación con ponderadores, experiencia mínima, equipo mínimo requerido.
- **RF-3.2** **Extracción estructurada de la tabla de multas** de las bases: causal, monto (UTM o % del contrato), quién la aplica, plazo de descargos. Alimenta M5 y M7 **antes** de que ocurra la multa.
- **RF-3.3** **Extracción de obligaciones contractuales**: informes periódicos y su frecuencia, hitos, plazos de entrega, garantías a constituir, seguros. Insumo directo de M5.
- **RF-3.4** **Scoring go/no-go** con criterios ponderables y editables:

| Criterio | Fuente |
|---|---|
| Encaje técnico | palabras clave + IA |
| Distancia y costo de traslado | geocodificación vs base más cercana |
| Capacidad disponible en el periodo | M4 |
| Margen esperado (monto vs costo estimado) | M8 histórico |
| Exposición a multas | RF-3.2 |
| Condiciones de pago vs caja | M6 |
| Historial con el organismo | histórico interno |
| Competencia esperada | RF-3.5 |

El score **sugiere**; Daniela decide. La decisión y su motivo quedan registrados.

- **RF-3.5 — Inteligencia competitiva.** Vía API por `CodigoOrganismo`, histórico de adjudicaciones del mismo organismo: quién ganó, a qué monto respecto del presupuesto disponible. Es lo que mejor calibra el precio de la oferta y casi nadie lo usa.
- **RF-3.6** Trazabilidad: cada análisis guarda modelo, versión de prompt, fecha y enlace al documento fuente.

---

### M4 — Pipeline, calendario y capacidad

- **RF-4.1** Kanban con los estados del ciclo de vida (sección 1).
- **RF-4.2** Cada tarjeta: responsable, checklist de M2, cuenta regresiva al cierre.
- **RF-4.3** **Calendario único** con todo: cierres, consultas, aperturas, adjudicaciones, hitos contractuales, entregas de informes, vencimientos de garantías, plazos de descargos. Exportable a iCal / Google Calendar.
- **RF-4.4 — Simulador de capacidad** (hallazgo 6): profesionales disponibles por región y periodo vs. carga que agregaría este contrato si se gana. Advierte de sobrecompromiso **antes** de postular.
- **RF-4.5** Escalamiento: si un ítem no avanza a X días del cierre, notifica al jefe de área.

---

### M5 — Adjudicación y puesta en marcha ⭐ *(módulo nuevo, el que pediste)*

**El problema que resuelve:** ganar la licitación es el momento de mayor riesgo operativo. Hay plazos legales cortos para firmar y constituir garantías, obligaciones que arrancan de inmediato, y es justo cuando el equipo está celebrando en vez de leyendo las bases otra vez.

- **RF-5.1 — Ingreso de una adjudicada.** Tres vías, todas terminan en el mismo lugar:
  1. Desde el pipeline (la licitación ya venía del radar y pasó a estado Adjudicada).
  2. **Pegando el código de licitación** (ej. `1509-5-L124`) → el sistema la trae de la API, dispara el scraper de M2 y el análisis de M3, aunque nunca haya pasado por el radar.
  3. Manual, para contratos fuera de Mercado Público.

- **RF-5.2 — Generación automática del plan de puesta en marcha.** A partir de las bases (RF-3.2 y RF-3.3), el sistema genera un **checklist con fechas calculadas** desde la fecha de adjudicación:

| Tarea generada | Origen |
|---|---|
| Firmar contrato (plazo desde adjudicación) | bases |
| Constituir garantía de fiel cumplimiento (monto, %, vigencia) | bases |
| Retirar garantía de seriedad de la oferta | M6 |
| Designar y notificar al profesional a cargo | bases (equipo mínimo) |
| Entregar credenciales / acreditaciones del equipo | bases |
| Contratar seguros exigidos | bases |
| Registrar hitos y fechas de informes periódicos | bases |
| Agendar visitas iniciales a obra | M8 |
| Verificar documentos vigentes al momento de contratar | M2.7 |

Cada tarea con responsable, fecha límite y estado. **Toda tarea generada por IA es editable y requiere confirmación humana** antes de quedar en firme.

- **RF-5.3 — Checklist preventivo de multas.** Desde la tabla de causales (RF-3.2) más el histórico de multas propias en causales similares (M7), el sistema genera controles recurrentes para el ITO: *"en este contrato la multa más probable es atraso en el informe mensual — vence el día 5 de cada mes."*
- **RF-5.4 — Ficha de contrato viva**: contraparte, monto, plazo, hitos, forma de pago, garantías, equipo asignado, obras asociadas, procedimiento aplicable (M0), estado de avance.
- **RF-5.5 — Vista "¿qué debo hacer?"** por contrato y por persona: tareas vencidas, de esta semana, próximas. Es la pantalla de inicio del ITO.
- **RF-5.6** Al cerrar el contrato: retiro de garantías, cálculo de rentabilidad real, registro de lecciones aprendidas que alimentan el scoring futuro.

---

### M6 — Estados de pago, garantías y flujo de caja

- **RF-6.1** Estados de pago: hito → informe entregado → recepción conforme → factura emitida → pago esperado → pago recibido. Fecha en cada paso.
- **RF-6.2** Cruce automático con órdenes de compra vía API (`CodigoProveedor` de la empresa) para detectar OC nuevas sin digitar.
- **RF-6.3 — Proyección de flujo de caja a 90+ días** (hallazgo 7): ingresos esperados según la modalidad de pago de cada contrato vs. egresos comprometidos (remuneraciones, viáticos, traslados). Alerta de déficit proyectado con al menos 60 días de anticipación.
- **RF-6.4 — Antigüedad de cobranza**: qué está atrasado, cuántos días, contra quién. Fundamenta un reclamo formal por atraso ante ChileCompra.
- **RF-6.5 — Control de garantías**: seriedad de la oferta y fiel cumplimiento, con vencimiento y alerta de retiro. Es plata inmovilizada que se olvida.
- **RF-6.6** Panel de riesgo de contraparte: historial de atrasos de pago por organismo, que se pondera en el scoring de M3.

---

### M7 — Multas

Dos mitades. La preventiva es la que importa.

- **RF-7.1** Registro: contrato, obra, fecha del hecho, causal, monto (UTM y CLP a la UTM del mes), estado (notificada / con descargos / aplicada / rebajada / anulada), documento, responsable.
- **RF-7.2 — Plazo de descargos con alerta de máxima prioridad.** Perder ese plazo es pagar sin defenderse. Debe ser la alerta más ruidosa del sistema: correo + WhatsApp + banner permanente hasta cerrarla.
- **RF-7.3** Análisis de patrones: por causal, obra, profesional, organismo, mes. Responde "¿en qué procesos poner más ojo?".
- **RF-7.4** Costo acumulado por contrato, en monto y como % del contrato.
- **RF-7.5** Retroalimentación al scoring: si un organismo o tipo de contrato concentra multas, baja su puntaje en M3.
- **RF-7.6** Biblioteca de descargos anteriores, reutilizable.

---

### M8 — Terreno, visitas y horas

- **RF-8.1** Programación de visitas con distancia y tiempo de traslado; **agrupación geográfica** para reducir viajes (hallazgo 5).
- **RF-8.2** Registro de visita en móvil, **offline-first** (en obra no hay señal), con fotos, geolocalización y sincronización posterior.
- **RF-8.3** Generación de informe de inspección desde plantilla, con fotos y observaciones ya cargadas.
- **RF-8.4** Registro de horas imputadas a contrato/obra. Alimenta el simulador de capacidad y la rentabilidad.
- **RF-8.5 — Rentabilidad real por contrato**: ingresos − (horas × costo hora + viáticos + traslados + multas). Es el número que hoy nadie tiene.

> ⚠️ **Restricción legal.** En Chile, reemplazar el libro de asistencia por un sistema electrónico propio requiere autorización de la Dirección del Trabajo, y el control con geolocalización tiene restricciones adicionales. **En v1 esto es control de gestión de horas por proyecto, no registro legal de asistencia.** Si se quiere que sea el registro oficial, consultar con abogado laboral y tramitar ante la DT antes de construirlo. Rehacerlo después sale caro.

---

### M9 — Reportes y Excel

- **RF-9.1** Importar las planillas actuales en el arranque (pedirlas en fase 0).
- **RF-9.2** Exportar cualquier vista a Excel, respetando los formatos que ya usan para reportar al SERVIU.
- **RF-9.3** Reportes programados por correo: semanal de oportunidades, mensual de multas y caja.
- **RF-9.4** Dashboard gerencial: oportunidades activas, tasa de adjudicación, caja proyectada, multas del trimestre, contratos por vencer, capacidad comprometida, rentabilidad por contrato.

---

### M10 — Notificaciones

- **RF-10.1** Canales: correo siempre; WhatsApp o Telegram para lo urgente (la gente en terreno no lee correo).
- **RF-10.2** Preferencias por usuario y tipo de evento, con niveles de urgencia. Sin esto, en una semana silencian todo y el sistema muere.
- **RF-10.3 — Ingesta del correo de Mercado Público**: leer la casilla que recibe las notificaciones del portal (IMAP o Gmail API), parsearlas y convertirlas en eventos del sistema. Resuelve el hallazgo 2 mejor que cualquier otra cosa.
- **RF-10.4** Toda alerta se cierra con una acción ("visto", "gestionado por X"). Alertas que nadie cierra son ruido.

---

### M11 — Repositorio documental y firma

- **RF-11.1** Repositorio único por licitación y por contrato, versionado, con hash.
- **RF-11.2** Trazar el estado del circuito de **firma electrónica avanzada**: qué documento espera firma de quién y desde cuándo. **No firmar dentro de la app** — está regulado y ya tienen la herramienta.
- **RF-11.3** Plantillas de anexos administrativos que se autocompletan con datos de la empresa.

---

## 6. Requerimientos no funcionales

| Categoría | Requerimiento |
|---|---|
| Disponibilidad | No crítica 24/7. Un job que falla reintenta y **avisa**; jamás falla en silencio. |
| Cuota API | Contador diario, degradación al 80%, batch 22:00–07:00. |
| Caché | Detalle de licitación cacheado por código; refrescar solo activas y las que cambiaron. |
| Scraping | Secuencial, con delay, identificable, tope diario configurable. |
| Trazabilidad | Auditoría de quién cambió qué, especialmente montos y multas. |
| Seguridad | Acceso por rol. Secretos (ticket, API keys, credenciales de correo) fuera del repositorio. |
| Datos personales | Verificar el estado de entrada en vigencia de la Ley 21.719 antes de construir M8. Minimizar datos, definir retención, no enviar datos de personas a APIs de terceros. |
| Móvil | M5.5 y M8 deben funcionar en teléfono; M8 además offline. PWA es suficiente. |
| Respaldos | Diario de base y repositorio. Probar la restauración una vez, de verdad. |
| Portabilidad | Todo exportable a Excel/CSV. |

---

## 7. Modelo de datos

```
Organismo          (codigo_mp, nombre, region, lista_negra, motivo, riesgo_pago)
Licitación         (codigo, organismo, tipo, estado, montos, fechas, flags, json_crudo,
                    origen: radar|manual|codigo_pegado)
  ├─ Anexo         (nombre, tipo, url, hash, version, descargado_en, texto_extraido)
  ├─ CambioDetectado (campo, valor_anterior, valor_nuevo, detectado_en)
  ├─ AnálisisIA    (resumen, criterios[], tabla_multas[], obligaciones[],
                    modelo, prompt_version, fecha)
  ├─ Evaluación    (score, criterios_puntuados[], decision, motivo, decidido_por, fecha)
  └─ Postulación   (estado, responsable, checklist[], oferta_monto, fecha_envio)

Contrato           (licitacion?, contraparte, monto, plazo, forma_pago, renovable,
                    fecha_adjudicacion, fecha_firma, estado)
  ├─ TareaPuestaEnMarcha (descripcion, origen, fecha_limite, responsable, estado,
                          generada_por_ia, confirmada_por)
  ├─ Hito          (descripcion, fecha_plan, fecha_real, estado)
  ├─ EstadoDePago  (hito, monto, fecha_factura, fecha_pago_esperada, fecha_pago_real)
  ├─ Garantía      (tipo, monto, emisor, vencimiento, estado, retirada_en)
  ├─ ControlPreventivo (causal_asociada, frecuencia, proxima_fecha, responsable)
  └─ Multa         (causal, monto_utm, monto_clp, fecha_hecho, fecha_notificacion,
                    plazo_descargos, estado, responsable, documento, monto_final)

Obra               (contrato, direccion, comuna, lat, lng)
  └─ Visita        (obra, profesional, fecha, informe, fotos[], geo, sincronizada)

Profesional        (nombre, rol, base_operacion, disponibilidad, costo_hora)
  └─ RegistroHoras (profesional, contrato, fecha, horas, tipo)

DocumentoEmpresa   (tipo, archivo, emision, vencimiento, vigente)
Procedimiento      (proceso, version, responsable, ultima_revision, contenido)
Alerta             (tipo, entidad, urgencia, destinatarios[], estado, cerrada_por)
CuotaAPI           (fecha, llamadas_usadas, llamadas_scraper)
```

---

## 8. Fases

Ordenadas por valor ÷ esfuerzo.

**Fase 0 — Preparación (sin código)**
Pedir el ticket con Clave Única (demora). Conseguir los Excel actuales y correos de notificación de ejemplo. Cerrar las preguntas de la sección 11. Juntar 5–10 licitaciones históricas reales como casos de prueba, incluyendo al menos una adjudicada con sus bases completas. Medir las líneas base.

**Fase 1 — MVP: radar + descarga**
M1 completo, M2 (scraper + checklist + biblioteca), M4 calendario simple, M10 correo.
*Éxito:* durante 2 semanas detecta todo lo que Daniela habría encontrado a mano, más algo que se le habría pasado, y descarga las bases sola.

**Fase 2 — Inteligencia**
M3 completo (resumen, tabla de multas, obligaciones, scoring, inteligencia competitiva) + M10 ingesta de correo.

**Fase 3 — Adjudicación y plata**
**M5 completo** + M6 + M7 + M9.

**Fase 4 — Terreno**
M8 + PWA offline + rentabilidad real.

**Transversal:** M0 desde el día 1. Cada módulo documenta su proceso al construirse.

---

## 9. Riesgos

| Riesgo | Impacto | Mitigación |
|---|---|---|
| Cambia la API de ChileCompra | Alto | Capa de adaptador desde el día 1 |
| Se agota la cuota diaria | Medio | Contador, caché, batch nocturno, degradación |
| Cambia el HTML del portal y muere el scraper | Alto | Scraper aislado, falla visible, plan B manual, tests contra HTML guardado |
| La IA extrae mal un monto o fecha | Alto | Dato de IA nunca sin fuente al lado; confirmación humana en M5 |
| Nadie lo usa y vuelven al Excel | **Muy alto** | Import/export Excel, Daniela involucrada desde fase 0, partir por lo que más duele |
| Problema legal con asistencia | Alto | v1 = control de gestión, no registro legal |
| Datos sensibles a APIs gratuitas | Medio | Prohibido por diseño; solo documentos públicos |
| Sobreingeniería en fase 1 | Alto | Fase 1 en producción antes de tocar la fase 2 |

---

## 10. Stack

- **Backend:** Python + FastAPI (encaja con scraping, PDF, OCR y Excel).
- **Base de datos:** PostgreSQL.
- **Jobs:** APScheduler o cron. No hace falta Celery para este volumen.
- **Scraping:** `httpx` + `selectolax`/BeautifulSoup. Headless (Playwright) solo si el portal lo exige.
- **PDF:** `pypdf`/`pdfplumber` + OCR (Tesseract) como fallback.
- **Frontend:** React + Tailwind, o server-rendered si prefieres menos piezas.
- **Archivos:** disco o S3-compatible, con hash.
- **Despliegue:** un VPS chico basta.

---

## 11. Preguntas abiertas (cerrar con Daniela)

Del levantamiento:
1. ¿Con quién es el contrato? El punteo quedó incompleto.
2. ¿Qué manual se revisa los viernes, con qué objetivo y quién responde?
3. El "pésimo servicio" de las municipalidades, ¿es como contraparte o algo más?
4. **Aparece el Servicio de Salud pagando a 90 días, pero el resto apunta al SERVIU. ¿Son dos clientes distintos?** Esto cambia el modelo de contratos y de caja.

De la app:

5. **¿Cuáles son hoy los criterios reales de Daniela para postular?** Sin esto no se puede programar el scoring. Es la conversación más valiosa del proyecto.
6. ¿Cuántas postulan al mes? ¿Cuántas revisan y descartan?
7. ¿Cuántas multas han tenido, por qué causales, de qué monto? ¿Hay registro?
8. Cuando ganan una licitación, **¿qué hacen hoy en los primeros 10 días?** Es el insumo directo del checklist de M5.
9. ¿Quién sube la oferta al portal?
10. ¿Qué Excel usan y cuáles no pueden abandonar?
11. ¿Cuántos profesionales, en qué regiones, cuántas obras cada uno?
12. ¿La asistencia hoy es libro físico, reloj control, o sistema autorizado por la DT?
13. ¿Hay contratos vigentes fuera de Mercado Público?
14. ¿Presupuesto para infraestructura y APIs?

---

## 12. Arranque en Claude Code

Orden de trabajo sugerido para la primera sesión:

1. **Scaffolding + adaptador de API.** Un script que traiga las licitaciones de un día y las guarde crudas. Verificar manualmente contra el portal que los datos calzan. No modelar la base todavía.
2. **Modelar la base** recién cuando tengas datos reales a la vista.
3. **Scraper de una licitación** que ya conozcas, guardando anexos con hash. Probar con una que tenga adenda.
4. **M1 completo** y usarlo en producción dos semanas antes de escribir una línea de M2 avanzado.

**Poner en el `CLAUDE.md` del repositorio:**
- Los límites de la sección 4.2 (cuota, horario nocturno, IP) como restricciones no negociables.
- Las 5 reglas duras de IA de la sección 4.4.
- La política de scraping de RF-2.3.
- La regla de que ningún dato generado por IA se muestra sin su fuente.
- Este PRD, y la instrucción de actualizarlo cuando la realidad contradiga un supuesto. Va a pasar.
