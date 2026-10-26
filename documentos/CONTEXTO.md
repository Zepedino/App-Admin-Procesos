# Contexto del proyecto — para retomar desde cero

**Última actualización:** 26 de octubre de 2026 · **Versión:** 0.1.0 · 13 commits · 87 tests en verde

Este documento existe para que alguien —o una conversación nueva con un
asistente— pueda continuar el trabajo sin haber estado presente. Contiene el
porqué de las decisiones, no solo el qué.

**Orden de lectura sugerido:** este documento → [`PRD-v1-sistema-licitaciones.md`](PRD-v1-sistema-licitaciones.md)
(la especificación funcional) → [`ESTADO.md`](ESTADO.md) (qué está construido) →
[`arquitectura.md`](arquitectura.md) (cómo). Las restricciones no negociables
están en [`../CLAUDE.md`](../CLAUDE.md).

---

## 1. Qué es esto

Sistema único de gestión de licitaciones y contratos para una **consultora de
inspección técnica de obra (ITO)** que trabaja principalmente para el **SERVIU**
en construcción de viviendas.

El ciclo completo vive en la misma aplicación: una licitación entra por el radar
y sale meses después como contrato cerrado con su rentabilidad real calculada.
**Es la misma entidad todo el rato**, no se re-digita en ningún punto.

```
Detección → Evaluación → Decisión (go/no-go) → Preparación de oferta → Ofertada
    → Adjudicada → Puesta en marcha → Ejecución → Estados de pago → Cierre
```

**Estado del proyecto:** fase 1. El radar (M1) opera en vivo contra la API real
de Mercado Público. Daniela ya vio el prototipo y lo aprobó.

### Glosario (hace falta para entender el dominio)

| Término | Significado |
|---|---|
| **ITO** | Inspección Técnica de Obra. El servicio que presta la consultora. |
| **FTO** | Fiscalización Técnica de Obras. **Como el SERVIU llama a lo mismo.** Ver §4.1. |
| **AFTO / ATO** | Asesoría a la FTO / Asesoría Técnica de Obra. Variantes del mismo servicio. |
| **SERVIU** | Servicio de Vivienda y Urbanización. Cliente principal. Hay uno por región. |
| **MINVU** | Ministerio de Vivienda y Urbanismo, del que depende el SERVIU. |
| **DS49 / DS27** | Programas habitacionales del MINVU. Aparecen en los títulos de licitación. |
| **PPP** | Pavimentos Participativos. Otro programa que licita el SERVIU. |
| **Mercado Público** | Portal de compras del Estado de Chile (mercadopublico.cl). |
| **ChileCompra** | La Dirección de Compras Públicas, que opera Mercado Público. |
| **Ticket** | La credencial de la API. Una por persona, se pide con Clave Única. |
| **Bases** | El pliego de condiciones de una licitación: administrativas y técnicas. |
| **Adenda** | Modificación de las bases después de publicadas. Puede mover el cierre. |

---

## 2. Quiénes son los usuarios

| Rol | Qué hace | Qué NO puede ver |
|---|---|---|
| **Gerencia (Daniela)** | Aprueba go/no-go. Decide a qué se postula. | — (ve todo) |
| **Encargado de licitaciones** | Revisa el radar, prepara ofertas. | Remuneraciones, rentabilidad |
| **Jefe de proyecto / ITO** | Sus contratos, visitas, informes, horas. | Lo ajeno a sus contratos |
| **Administración y finanzas** | Estados de pago, garantías, cobranza, multas. | Costos de personal |
| **Admin** | Configuración, usuarios, integraciones. | — |

Son **3 a 10 personas**. No hace falta arquitectura de escala; sí control de
acceso, porque hay datos de multas y remuneraciones.

---

## 3. Restricciones que el código hace cumplir

No son recomendaciones. Están implementadas y hay tests que fallan si se rompen.

### API de Mercado Público

- **10.000 llamadas al día por ticket.** Tope duro. Se cuentan antes de llamar y
  se persisten: un reinicio no regala cuota ya gastada.
- **Al 80 % el sistema degrada**: solo refresca lo que cierra en menos de 48 h, y
  avisa una sola vez (avisar en cada llamada hace que se silencie el aviso).
- **Cargas masivas solo entre 22:00 y 07:00** hora de Chile.
- **3 segundos entre llamadas.** Medido, no estimado (§4.2).
- **Toda llamada pasa por `ProcurementProvider`.** Un test falla si aparece una
  URL de la API en cualquier otro archivo.

### Inteligencia artificial (aún no se usa, pero la capa existe)

- Solo **documentos públicos** van al LLM. La guarda corta la operación y además
  detecta RUT de personas y remuneraciones en documentos mal clasificados.
- La IA **resume y pre-clasifica, no decide**.
- **Ningún dato de IA se muestra sin su fuente.** `CampoExtraido` no se puede
  construir sin documento y página de origen: es una garantía estructural, no
  una convención.

### Transversales

- Ningún job falla en silencio: reintenta, registra y emite evento.
- Auditoría automática de quién cambió qué (177 registros hasta ahora).
- Secretos solo por variable de entorno. `.env` nunca se versiona.

---

## 4. Hallazgos que cambiaron el diseño

Esta sección es la más importante para retomar. Son cosas que **solo se
descubrieron usando datos reales** y que contradicen supuestos razonables.

### 4.1 El SERVIU no dice «inspección técnica»

El perfil inicial buscaba las palabras del PRD: *inspección técnica*, *ITO*,
*asesoría a la inspección*, *supervisión de obras*.

Sobre **8.132 licitaciones reales de 7 días hábiles**, el radar capturó **cero
del SERVIU**, que es el cliente principal. No porque no hubiera: el SERVIU las
titula **«Fiscalización Técnica de Obras» (FTO)**. Se perdían 11 del rubro
exacto, varias de los programas DS49 y DS27.

**Consecuencia:** el perfil ahora incluye `fiscalizacion tecnica de obras`,
`fiscalizacion tecnica`, `FTO` y `AFTO`. El PRD se actualizó (RF-1.2bis).

### 4.2 El listado diario no dice de quién es cada licitación

La consulta por fecha devuelve **solo cuatro campos**: código, nombre, estado y
fecha de cierre. **No incluye el organismo comprador.** Así que filtrar por «es
del SERVIU» en la pasada barata es imposible: solo se puede por palabras del
título.

Y el SERVIU publica licitaciones llamadas únicamente **«LP 110-2026»**. Ningún
perfil de palabras clave las encontraría jamás.

**Consecuencia — vigilancia dirigida:** los organismos marcados se consultan por
su código (`CodigoOrganismo` + `estado=activas`), lo que devuelve todo lo que
tengan abierto. 13 SERVIU = 13 llamadas de las 10.000. Trajo 40 licitaciones que
el filtro por palabras nunca habría visto.

**Detalle que costó encontrarlos:** en el catálogo de ChileCompra solo **uno** de
los 13 se llama «SERVIU» (el de Magallanes). Los otros doce figuran como
«SERVICIO DE VIVIENDA Y URBANIZACION ⟨región⟩». Buscar la sigla encontraba uno de
trece.

### 4.3 El límite de frecuencia es real y medible

Los HTTP 429 no venían de compartir el ticket de pruebas: siguen apareciendo con
ticket propio. Es límite por IP, como advierte el PRD.

Medido con seis llamadas seguidas:

| Intervalo | Respuestas 429 |
|---|---|
| 0,6 s | 2 de 6 |
| 1,5 s | 1 de 6 |
| **3,0 s** | **0 de 6** |

Sin espaciarlas, el 85 % de las llamadas necesitaba reintento. Cada reintento
gasta cuota y 2 s de backoff, e insiste sobre un servicio que acaba de pedir que
bajemos el ritmo. **El intervalo configurado es 3,0 s** (`MP_DELAY_ENTRE_LLAMADAS_SEG`).

### 4.4 Un ticket inválido responde HTTP 200

Si el ticket está mal copiado, la API **no** devuelve un error HTTP: devuelve
200 con un cuerpo `{"Codigo":…, "Mensaje":"Ticket no válido"}`. Sin una
comprobación explícita, el sistema parecería funcionar y simplemente no traería
nada.

Por eso existe `doctor --probar-api`, que hace una llamada real y lo dice sin
ambigüedad.

### 4.5 «ito» calza dentro de «Tránsito»

Buscar la subcadena `"ito "` marcaba *«Suministro señaléticas de Tránsito 2026»*
como candidata. Por eso el emparejamiento usa **límites de palabra**, no
subcadenas, y el resultado guarda **qué palabra hizo match** para poder
auditarlo. Si el encargado no ve por qué una licitación apareció en su bandeja,
no confía en el radar.

---

## 5. Bugs encontrados y corregidos

Vale la pena conocerlos: varios eran invisibles y volverían si alguien
«simplifica» el código.

| Bug | Síntoma | Causa |
|---|---|---|
| **Deadlock de sincronización** | Se guardaba **1 licitación por día** y el resto moría con «database is locked», después de gastar la cuota | La transacción de lectura envolvía el bucle de llamadas HTTP, y dentro el contador de cuota abría otra |
| **Lista negra inoperante** | Las municipalidades entraban a la bandeja pese al hallazgo 8 | El campo y la pantalla existían; el filtro nunca los consultaba |
| **Fechas sin zona** | El detector de adendas reportaba cambios inexistentes en cada sincronización | SQLite devolvía *naive* lo que se guardaba *aware*. Resuelto con el tipo `FechaHoraUTC` |
| **`licitaciones_por_organismo` vacío** | Devolvía siempre 0 resultados | Le faltaba `estado=activas` |
| **«job duplicado»** | `crear_app` dos veces en un proceso reventaba | La guarda que debía evitarlo buscaba un job que nunca se registra |
| **Lanzador sin migraciones** | Un cambio de modelo nunca llegaba a una base ya creada | Usaba `create_all` en vez de Alembic |
| **Botón que parecía colgado** | «Sincronizar ayer» dejaba el navegador más de un minuto sin respuesta | Corría dentro de la petición; con 3 s entre llamadas, se veía como un cuelgue |
| **«ayer» en zona equivocada** | En un host UTC (Render) sincronizaría el día equivocado de noche | Usaba el reloj del sistema en vez del de Chile |

---

## 6. Arquitectura en una página

```
iniciar.py            ← ejecutar esto levanta todo. Solo stdlib, a propósito.
backend/
  app.py              fábrica de la aplicación
  consola.py          comandos de operación y diagnóstico
  plantillas.py       motor Jinja y filtros de presentación
  nucleo/             config, BD, auditoría, eventos, RBAC, planificador, registro
  conectores/         adaptadores externos, intercambiables por contrato
    mercado_publico/  API de ChileCompra (+ proveedor de fixtures)
    ia/               LLM con las reglas duras implementadas
    archivos/         almacenamiento versionado por hash
    avisos/           correo, WhatsApp, consola
  modulos/            un paquete por módulo del PRD (m0_procesos … m11_documental)
frontend/
  plantillas/         HTML Jinja (base/ y paginas/)
  estaticos/          CSS propio, sin build ni CDN
migraciones/          Alembic
pruebas/              87 tests, incluidos los de arquitectura
documentos/           PRD, estado, arquitectura, decisiones (ADR)
datos_demo/           datos reales versionados para arrancar con contenido
datos/                base de datos y archivos (NO se versiona)
```

**Las tres reglas de dependencia** (testeadas en `pruebas/test_arquitectura.py`):

1. `nucleo/` no importa `modulos/` ni `conectores/`.
2. `modulos/` no importa otro `modulos/`: se comunican por el **bus de eventos**
   (`nucleo/eventos.py`) o por el **registro de pendientes** (`nucleo/pendientes.py`).
3. `conectores/` no importa `modulos/`.

**Agregar un módulo son dos pasos:** crear el paquete con la anatomía de
`CLAUDE.md` §5, y añadirlo a `_MANIFIESTOS` en `backend/modulos/__init__.py`.
Si hiciste falta tocar `nucleo/` o `app.py`, el diseño falló — y hay un test que
lo detecta.

### El embudo de cuota (la decisión central de M1)

```
  1 llamada  →  listado del día: ~1.200 licitaciones (solo 4 campos)
       ↓
  0 llamadas →  filtro por nombre contra el perfil: ~1.200 → 2-6 candidatas
       ↓
  N llamadas →  detalle completo, una por candidata
       ↓
  0 llamadas →  reevaluación con items, categorías UNSPSC, región y monto
```

Sin el embudo, un día costaría ~1.200 llamadas y **tres días agotarían el
ticket**.

---

## 7. Estado por módulo

| Módulo | Fase | Estado | Qué falta |
|---|---|---|---|
| **M0 Procesos** | 0 | **parcial** | Editor de procedimientos en la UI, seguimiento de cambios normativos |
| **M1 Radar** | 1 | **parcial** | Geocodificación para el criterio de distancia, enganche con M2 |
| M2 Fichas y anexos | 1 | planificado | **Bloqueado:** revisar términos de uso del portal |
| M3 Análisis IA y scoring | 2 | planificado | **Bloqueado:** criterios reales de Daniela |
| M4 Pipeline y calendario | 1 | planificado | Los datos de fechas ya se guardan; falta la vista |
| M5 Adjudicación | 3 | planificado | **Bloqueado:** qué hacen hoy en los primeros 10 días |
| M6 Pagos y caja | 3 | planificado | **Bloqueado:** ¿SERVIU y Servicio de Salud son dos clientes? |
| M7 Multas | 3 | planificado | — |
| M8 Terreno y horas | 4 | planificado | **Restricción legal:** v1 es control de gestión, no registro de asistencia |
| M9 Reportes y Excel | 3 | planificado | — |
| M10 Notificaciones | 1 | planificado | La capa de proveedores existe; falta el módulo de negocio |
| M11 Documental y firma | 3 | planificado | El almacenamiento por hash ya existe |

La misma información, generada desde el código, está en `/sistema/modulos`.

---

## 8. Cómo arrancar

```bash
# Windows: doble clic en "Iniciar aplicacion.bat"
# Cualquier sistema:
python iniciar.py
```

El lanzador crea el entorno, instala dependencias, genera `.env`, aplica
migraciones, carga 134 licitaciones reales de `datos_demo/` y abre el navegador.
Primera vez: 1-2 minutos. Después: 5 segundos.

### Comandos de operación

```bash
python -m backend.consola doctor                  # entorno, cuota, esquema
python -m backend.consola doctor --probar-api     # UNA llamada real: ¿sirve el ticket?
python -m backend.consola sync-dia 2026-10-15     # sincroniza un día
python -m backend.consola vigilar --listar        # organismos bajo vigilancia
python -m backend.consola run-job                 # lista las tareas programadas
python -m backend.consola demo --exportar         # regenera datos_demo/
pytest                                            # 87 tests
```

### El ticket

Se pide gratis en <https://www.chilecompra.cl/api/> con Clave Única. Es **uno por
persona**, no de la empresa: si esa persona se va, puede dejar de servir. Guía
completa en [`ticket-mercado-publico.md`](ticket-mercado-publico.md), incluido
qué hacer si no llega el correo (pasó: la dirección estaba mal escrita y el
mensaje rebotó).

---

## 9. Lo que bloquea el avance

**Preguntas para Daniela** (las tres primeras bloquean módulos completos):

1. **¿Cuáles son sus criterios reales para postular?** El PRD la llama «la
   conversación más valiosa del proyecto». Bloquea M3. Ahora hay material
   concreto: 134 licitaciones reales que puede marcar sí/no, que funciona mucho
   mejor que preguntarle los criterios en abstracto.
2. **¿Qué hacen hoy en los primeros 10 días tras ganar?** Bloquea M5.
3. **¿SERVIU y Servicio de Salud son dos clientes distintos?** El levantamiento
   menciona al Servicio de Salud pagando a 90 días, pero el resto apunta al
   SERVIU. Cambia el modelo de contratos y de caja. Bloquea M6.
4. **Las licitaciones del MOP** («asesoría a la inspección fiscal») — decisión
   tomada provisionalmente: se dejan entrar porque Daniela quiere expandirse. Se
   afinará después.

**Técnico, antes de producción:**

- **Autenticación.** La matriz de permisos existe y está testeada, pero falta el
  login que la active. Hoy todo se audita como `sistema`.
- **Respaldos.** Supabase respalda la base; los archivos de `datos/` no, porque
  el disco de Render es efímero. Al activar M2 hay que mover el almacenamiento a
  S3 o Supabase Storage.
- **Revisar los términos de uso del portal** antes de activar el scraper.

---

## 10. Próximos pasos sugeridos

En orden de valor sobre esfuerzo:

1. **Calibrar el perfil con Daniela** sobre las 134 reales. Desbloquea M3 y
   mejora el radar de inmediato. No requiere código.
2. **M2 — descarga de bases y anexos.** El módulo que más tiempo ahorra según el
   PRD. No depende del ticket (usa la ficha pública). Requiere antes el punto de
   términos de uso.
3. **M4 — calendario y pipeline.** Los datos ya están guardados; falta la vista.
   Barato y visible.
4. **Autenticación.** Necesaria antes de que esto corra con datos reales de
   multas o remuneraciones.

---

## 11. Notas para quien retome

- **El PRD se actualiza cuando la realidad lo contradice.** Ya pasó dos veces
  (RF-1.2bis y el hallazgo FTO). Está escrito en `CLAUDE.md` y no es decorativo.
- **No hay datos inventados en ninguna parte.** Los fixtures de `pruebas/` son
  respuestas literales de la API. Si falta un fixture, el proveedor devuelve
  vacío y lo registra en vez de adivinar.
- **`documentos/ESTADO.md` dice qué está construido de verdad.** Mantenerlo
  honesto es obligatorio: es lo que evita prometer lo que no está.
- **Los ADR en `documentos/decisiones/`** explican por qué se eligió cada cosa,
  incluidas las alternativas descartadas.
- Hay un generador de **instantánea HTML navegable** (`consola informe --app`)
  que se usó para mostrarle el prototipo a Daniela. Ya cumplió su función; no es
  el foco del trabajo.
