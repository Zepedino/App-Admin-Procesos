# SGL — Sistema Único de Gestión de Licitaciones y Contratos

Consultora ITO / SERVIU. Todo el ciclo de vida de una licitación en una sola
aplicación: desde que aparece en el radar de Mercado Público hasta que el
contrato se cierra con su rentabilidad real calculada.

Especificación funcional: [`docs/PRD-v1-sistema-licitaciones.md`](docs/PRD-v1-sistema-licitaciones.md)
Restricciones no negociables: [`CLAUDE.md`](CLAUDE.md)
Qué está construido de verdad: [`docs/ESTADO.md`](docs/ESTADO.md)

---

## Arrancar en local

```bash
python -m venv .venv
.venv/Scripts/activate          # Windows;  en Linux/macOS: source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
python -m sgl.cli init-db --con-semilla
python -m sgl.cli serve --reload
```

Abre <http://localhost:8000>.

Sin `MP_TICKET` el sistema funciona igual: usa respuestas **reales** de la API
guardadas en `tests/fixtures/api/`, y lo advierte en cada pantalla. No hay datos
inventados en ninguna parte.

---

## Comandos

```bash
python -m sgl.cli doctor                 # entorno, conectividad, cuota, módulos
python -m sgl.cli init-db --con-semilla  # crea tablas + perfil y ciclo de vida iniciales
python -m sgl.cli sync-dia 2026-09-04    # sincroniza un día (acepta también 04092026)
python -m sgl.cli sync-dia --limite 20   # ayer, con tope de llamadas de detalle
python -m sgl.cli traer 1509-5-L126      # trae una licitación por código (RF-5.1)
python -m sgl.cli capturar-fixture 1509-5-L126   # guarda una respuesta real como fixture
python -m sgl.cli run-job                # lista los jobs
python -m sgl.cli run-job m1_radar.pull_liviano  # ejecuta uno a mano
python -m sgl.cli estado                 # resumen del contenido
pytest                                   # 77 tests, incluidos los de arquitectura
```

`doctor` es lo primero que hay que correr cuando algo no funciona: la mayoría de
los problemas de este tipo de sistema son de configuración, no de lógica.

---

## Estructura

```
src/sgl/
  core/        núcleo: config, BD, auditoría, eventos, RBAC, planificador, registro
  providers/   adaptadores externos, intercambiables por contrato
     procurement/   API de Mercado Público (+ proveedor de fixtures)
     llm/           IA, con las reglas duras del PRD §4.4 implementadas
     storage/       archivos versionados por hash SHA-256
     notify/        correo, WhatsApp, consola
  modules/     un paquete por módulo del PRD (m0_procesos … m11_documental)
  web/         plantillas Jinja + CSS propio, sin build
tests/
  fixtures/api/    respuestas REALES de la API, capturadas y versionadas
docs/
  PRD-…            especificación funcional
  ESTADO.md        qué está construido, qué es esqueleto, qué no existe
  arquitectura.md  cómo está armado y por qué
  decisiones/      ADR numerados
```

Cada módulo trae su propio `PROCESO.md`: el procedimiento operativo escrito que
exige RF-0.1, junto al código y no en una carpeta que nadie abre.

---

## Cómo agregar un módulo

1. Crear `src/sgl/modules/mN_nombre/` con la anatomía descrita en
   [`CLAUDE.md`](CLAUDE.md) §5.
2. Exponer un `MODULO: Modulo` en su `__init__.py`.
3. Añadirlo a `_MANIFIESTOS` en `src/sgl/modules/__init__.py`.

No hay paso 4. **Si tuviste que tocar `core/` o `main.py` para agregar
funcionalidad, el diseño falló** — y hay tests de arquitectura que lo detectan.

Los módulos no se importan entre sí: se comunican por el bus de eventos
(`core/eventos.py`). Ver [`docs/arquitectura.md`](docs/arquitectura.md) §2.

---

## Restricciones que el código hace cumplir

No son documentación; están implementadas y testeadas.

- **10.000 llamadas diarias a la API**, contadas antes de llamar y persistidas.
  Al 80 % el sistema degrada y avisa una sola vez.
- **Cargas masivas solo entre 22:00 y 07:00** hora de Chile.
- **Toda llamada pasa por `ProcurementProvider`.** Un test falla si aparece una
  URL de la API en cualquier otro archivo.
- **Solo documentos públicos van al LLM.** La guarda corta la operación, y
  además detecta RUT de personas y remuneraciones en documentos mal clasificados.
- **Ningún dato de IA sin su fuente.** `CampoExtraido` no se puede construir sin
  documento y página de origen.
- **Ningún job falla en silencio**: reintenta, registra y emite evento.
- **Auditoría automática** de quién cambió qué, con énfasis en montos y estados.

---

## Despliegue

Ver [`docs/despliegue.md`](docs/despliegue.md). Resumen: Render (web service) +
Supabase (Postgres). Un solo servicio sirve API y páginas.

---

## Estado

Fase 1 en construcción. M0 y M1 operativos y verificados contra la API real;
M2–M11 declarados en el registro con su estado real, visible en `/sistema/modulos`.

Lo que bloquea el avance está listado en la portada de la aplicación y en
[`docs/ESTADO.md`](docs/ESTADO.md).
