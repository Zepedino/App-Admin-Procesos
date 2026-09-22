# Arquitectura

Cómo está armado el sistema y, sobre todo, **por qué**. Si vas a modificar algo,
lee la sección 2: las reglas de dependencia son lo que mantiene el sistema
reparable por partes, y están respaldadas por tests que fallan si se rompen.

---

## 1. Vista general

```
                      ┌──────────────────────────────────┐
                      │            web/                  │
                      │  Jinja + CSS propio, sin build   │
                      └───────────────┬──────────────────┘
                                      │
       ┌──────────────────────────────┴──────────────────────────────┐
       │                        modules/                             │
       │   m0_procesos   m1_radar   m2_fichas …   m11_documental     │
       │        ▲            ▲                                       │
       │        └──── bus de eventos ────┘   (nunca se importan)     │
       └──────────────────────────────┬──────────────────────────────┘
                                      │
       ┌──────────────────────────────┴──────────────────────────────┐
       │                          core/                              │
       │  config · db · modelo_base · auditoría · eventos ·          │
       │  seguridad · planificador · registro · pendientes · tiempo  │
       └──────────────────────────────┬──────────────────────────────┘
                                      │
       ┌──────────────────────────────┴──────────────────────────────┐
       │                       providers/                            │
       │  procurement (Mercado Público) · llm · storage · notify     │
       └──────────────────────────────┬──────────────────────────────┘
                                      │
              API ChileCompra · Gemini · disco/S3 · correo/WhatsApp
```

Las flechas apuntan hacia abajo y **nunca hacia arriba**. `core` no sabe qué
módulos existen; `providers` no sabe qué es una licitación para el negocio.

---

## 2. Reglas de dependencia

Están en `CLAUDE.md` §5 y se verifican en `tests/test_arquitectura.py`.

| Regla | Por qué existe | Test |
|---|---|---|
| `core/` no importa `modules/` ni `providers/` | Si el núcleo importa un módulo, quitar ese módulo rompe el arranque completo | `test_core_no_importa_modulos_ni_providers` |
| `providers/` no importa `modules/` | Un adaptador externo no puede depender de lógica de negocio | `test_providers_no_importan_modulos` |
| Un módulo no importa otro módulo | Permite construir M5 sin tocar M1, y quitar M7 sin romper M3 | `test_modulos_no_se_importan_entre_si` |
| Solo el adaptador habla con la API | Si aparece una URL fuera de ahí, alguien se saltó cuota, caché y reintentos | `test_solo_el_adaptador_habla_con_mercadopublico` |
| Los eventos se declaran en el catálogo | Un emisor y un suscriptor que difieren por un tipeo fallan **en silencio** | `test_todo_evento_publicado_esta_en_el_catalogo` |
| Todo módulo declara qué RF cubre | Sin eso no se puede auditar el avance | `test_los_manifiestos_declaran_requisitos_del_prd` |

### Cuando un módulo necesita algo de otro

No lo importa. Hay dos mecanismos, según el caso:

**a) Reaccionar a algo que pasó → bus de eventos** (`core/eventos.py`)

```python
# M2, en su registrar_suscripciones()
BUS.suscribir(Eventos.LICITACION_MARCADA_INTERESA, encolar_descarga_de_anexos)
```

M1 emite el evento sin saber que M2 existe. Si M2 no está construido, no pasa
nada. Si M2 falla, M1 no se entera (el bus registra el error y sigue).

**b) Aportar información al conjunto → registro de extensión** (`core/pendientes.py`)

La revisión de los viernes (RF-0.3) necesita contar pendientes vencidos de todo
el sistema, pero M0 no puede importar M1, M5, M6 ni M7. Entonces cada módulo se
inscribe:

```python
# M1, en su registrar_suscripciones()
registrar_contador("Cambios críticos sin revisar", contar_cambios_sin_ver,
                   modulo="m1_radar", ruta="/radar/")
```

Cuando se construya M7, sus plazos de descargos vencidos aparecerán en la
revisión del viernes **sin tocar una línea de M0**.

---

## 3. Anatomía de un módulo

Todos idénticos. Es lo que hace el sistema auditable: sabes dónde mirar sin
explorar.

```
modules/mN_nombre/
  __init__.py   MANIFIESTO: id, nombre, RF que cubre, fase, estado, router, jobs
  models.py     tablas SQLAlchemy propias
  schemas.py    pydantic de entrada/salida (si hace falta)
  services.py   lógica de negocio (testeable sin HTTP)
  filtro.py     lógica pura, sin BD ni red (cuando hay reglas complejas)
  jobs.py       tareas programadas + registrar_jobs() + registrar_suscripciones()
  routes.py     endpoints y vistas
  PROCESO.md    el procedimiento operativo escrito (M0, RF-0.1)
```

**Agregar un módulo son dos pasos:** crear el paquete y añadirlo a `_MANIFIESTOS`
en `modules/__init__.py`. No hay paso tres. Si tuviste que tocar `core/` o
`main.py`, el diseño falló.

El manifiesto declara su estado real (`completo` / `parcial` / `esqueleto` /
`planificado`), y `/sistema/modulos` se genera desde ahí. No se puede
desactualizar porque no se escribe a mano.

---

## 4. La capa de compras públicas

Es la pieza con más restricciones del sistema, y por eso la más aislada.

### El embudo de cuota

Esta es **la** decisión de diseño de M1. Verificado contra la API real:

```
  1 llamada  →  listado del día: 1.214 licitaciones
                (solo CodigoExterno, Nombre, CodigoEstado, FechaCierre)
       ↓
  0 llamadas →  filtro por nombre contra el perfil: 1.214 → 3 candidatas
       ↓
  3 llamadas →  detalle completo, una por candidata
       ↓
  0 llamadas →  reevaluación con items, categorías UNSPSC, región y monto
```

Sin ese embudo, sincronizar un día costaría 1.215 de las 10.000 llamadas
diarias y **tres días agotarían el ticket**.

### Qué pasa cuando algo falla

| Situación | Comportamiento |
|---|---|
| HTTP 429 / 5xx | 3 reintentos con backoff exponencial (2 s, 4 s, 8 s) |
| Agotados los reintentos | Sirve caché **vencida** marcada como tal, antes de rendirse |
| Sin caché tampoco | `ProveedorNoDisponible` — falla visible, con bitácora |
| JSON que no es JSON | `RespuestaInesperada` — señal de mantenimiento del portal |
| Falta la clave `Listado` | `RespuestaInesperada` — el contrato cambió, no adivinamos |
| Cuota al 80 % | Modo degradado: solo se refresca lo que cierra en < 48 h. Avisa **una vez** |
| Cuota al 100 % | `CuotaAgotada` — no reintentable hoy |
| Fuera de 22:00–07:00 | El job nocturno no corre y lo registra |

La cuota se reserva **antes** de llamar, porque una llamada que falla también
consumió cuota del lado de ChileCompra.

### TTL de caché por estado

Una licitación `Publicada` cambia (adendas, aclaraciones, cambio de cierre);
una `Cerrada` o `Adjudicada` es prácticamente inmutable. Cachearlas igual sería
gastar cuota en lo que no cambia y perderse lo que sí.

| Estado | TTL |
|---|---|
| Publicada (5) o desconocido | 4 horas |
| Cerrada, Desierta, Adjudicada, Revocada, Suspendida | 30 días |
| Listado de un día pasado | 30 días |
| Listado de hoy | 4 horas |

### Cambiar de proveedor

ChileCompra está desarrollando un portal API unificado que reemplazará al actual.
Cuando salga: se escribe otra clase que implemente `ProcurementProvider`, se
cambia la fábrica en `providers/procurement/__init__.py`, y se borra
`mercadopublico.py`. **Nada más del sistema se entera.**

---

## 5. Las reglas duras de IA, como código

Las cinco reglas del PRD §4.4 están implementadas, no documentadas:

| Regla | Implementación |
|---|---|
| 1. Solo documentos públicos | `verificar_documento_publico()` **corta** la operación. Además detecta RUT de persona, remuneraciones y cuentas bancarias en documentos marcados como públicos: red de seguridad ante el error de clasificación humana |
| 2. La IA no decide | El contrato solo devuelve `ResultadoIA`, que es información con procedencia. No hay forma de que devuelva una acción |
| 3. Nada sin su fuente | `CampoExtraido` **no se puede construir** sin un `FuenteDato` con documento y página. Garantía estructural, no convención |
| 4. Proveedor intercambiable | `LLMProvider` abstracto. Cambiar de Gemini o pasar al tier pagado es escribir una subclase |
| 5. Correcciones registradas | `CampoExtraido.corregir()` guarda quién y cuándo. Corregido por un humano, deja de marcarse como output de IA |

El detalle que hace que esto no se pueda saltar: `analizar()` es **concreto** y
aplica la guarda; `_analizar()` es el abstracto. Una implementación nueva no
puede omitir la verificación por descuido.

---

## 6. Decisiones de datos

### Todo en UTC, con zona

`core/modelo_base.FechaHoraUTC` fuerza que todo instante entre y salga como UTC
consciente de zona. Postgres guarda la zona; SQLite no. Sin este tipo, el mismo
instante se guardaba como *aware* y se leía como *naive*, y el detector de
cambios de RF-1.4 reportaba adendas inexistentes en cada sincronización.

Este bug apareció de verdad durante la construcción y lo cazó un test.

### Se guarda el JSON crudo

`Licitacion.json_crudo` guarda la respuesta completa de la API. Ocupa espacio y
vale la pena: permite reprocesar sin gastar cuota cuando descubramos que hacía
falta un campo que hoy no mapeamos.

### Dos ejes de estado, no uno

- `codigo_estado` — lo que dice el portal (Publicada, Cerrada, Adjudicada…)
- `estado_seguimiento` — lo que decimos nosotros (nueva, interesa, descartada…)

Son independientes. Confundirlos es el error clásico de estos sistemas: una
licitación puede estar Publicada en el portal y Descartada para nosotros.

### Los motivos de descarte son un enum

RF-1.5: *"en 6 meses estos datos dicen si los criterios sirven"*. Sobre texto
libre no se puede agregar nada. Por eso el motivo es tipificado y obligatorio, y
`Otro` exige explicación escrita.

---

## 7. Auditoría

Dos mecanismos que se complementan:

1. **Automática** — listeners de SQLAlchemy sobre `before_flush`. Un modelo
   marcado con `Auditable` registra sus cambios de columna. Nadie puede
   olvidarse de auditar.
2. **Explícita** — `registrar()` para hechos de negocio: un go/no-go, un
   descarte con motivo, una alerta cerrada. Un cambio de columna no cuenta la
   intención.

Los campos de `CAMPOS_CRITICOS` (montos, scores, estados, decisiones) se
auditan siempre, aunque el modelo restrinja qué campos vigila.

Las filas de auditoría se identifican por clave natural cuando existe:
`Licitacion 425-57-LR26` dice algo; `Licitacion 2` no.

---

## 8. Frontend

Server-rendered con Jinja, CSS propio en un archivo, sin build y sin CDN.

**Por qué:** el criterio del proyecto es que sea auditable y reparable. Un
archivo CSS que se lee de arriba abajo cumple eso; una cadena de build con
PostCSS y Tailwind, no. Además permite desplegar front y backend como una sola
pieza, que es lo que se pidió.

El sistema de diseño son tokens CSS (`:root`), y los componentes solo consumen
tokens. Cambiar la paleta es cambiar el bloque `:root`. Hay modo oscuro
automático por `prefers-color-scheme`.

Dos cosas viven en el layout base y no en cada página, para que ninguna pantalla
las pueda omitir por descuido:

- El aviso de que los datos **no** vienen de la API en vivo.
- El aviso de cuota en modo degradado.

Cuando llegue M8 (registro de visitas offline en terreno), esa parte sí necesita
ser una PWA con service worker. Es un añadido aislado, no un cambio de enfoque.
