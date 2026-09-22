# SGL — Sistema Único de Gestión de Licitaciones y Contratos

Consultora ITO / SERVIU. Todo el ciclo de vida de una licitación en una sola
aplicación: desde que aparece en el radar de Mercado Público hasta que el
contrato se cierra con su rentabilidad real calculada.

---

## Cómo abrir la aplicación

**Windows:** doble clic en **`Iniciar aplicacion.bat`**

**macOS o Linux:** doble clic en `iniciar.sh`, o en una terminal `./iniciar.sh`

**Desde VS Code o PyCharm:** abrir `iniciar.py` y pulsar el botón Run.

No hace falta escribir nada. El lanzador se encarga solo de:

1. Verificar que haya Python 3.11 o superior.
2. Crear el entorno aislado (`.venv`) e instalar las dependencias.
3. Crear el archivo de configuración `.env`.
4. Crear la base de datos con sus datos iniciales.
5. Publicar los procedimientos escritos dentro de la app.
6. Abrir el navegador cuando el servidor ya está respondiendo.

**La primera vez tarda uno o dos minutos** porque descarga las librerías. Las
siguientes, segundos. Para detenerla: `Ctrl+C` o cerrar la ventana.

> Si algo falla, el lanzador dice **qué hacer**, no solo qué se rompió.
> Para ver el detalle técnico: `python iniciar.py --detalle`

Sin el ticket de Mercado Público el sistema funciona igual: usa respuestas
**reales** de la API guardadas en `pruebas/fixtures/api/`, y lo advierte en cada
pantalla. No hay datos inventados en ninguna parte.

---

## Qué hay dentro

```
iniciar.py              ← ejecutar esto abre la aplicación
Iniciar aplicacion.bat  ← atajo de Windows (doble clic)

backend/                TODO LO QUE HACE
  app.py                  arma la aplicación
  consola.py              comandos de operación y diagnóstico
  plantillas.py           motor de plantillas y formato de fechas y montos
  nucleo/                 configuración, base de datos, auditoría, eventos, permisos
  conectores/             conexiones al mundo exterior, reemplazables
    mercado_publico/        API de ChileCompra
    ia/                     inteligencia artificial
    archivos/               guardado de documentos con control de versiones
    avisos/                 correo, WhatsApp, consola
  modulos/                un paquete por módulo del PRD (m0_procesos … m11_documental)

frontend/               TODO LO QUE SE VE
  plantillas/             páginas HTML
  estaticos/              estilos

pruebas/                tests automáticos (79)
documentos/             PRD, estado real, arquitectura y decisiones
datos/                  base de datos y archivos descargados (no se versiona)
```

Cada módulo trae su propio `PROCESO.md`: el procedimiento operativo escrito que
exige RF-0.1, junto al código y no en una carpeta que nadie abre. La app los
publica en `/procesos/`.

---

## Documentación

| Documento | Para qué |
|---|---|
| [`documentos/PRD-v1-sistema-licitaciones.md`](documentos/PRD-v1-sistema-licitaciones.md) | Qué debe hacer el sistema |
| [`documentos/ESTADO.md`](documentos/ESTADO.md) | Qué está construido **de verdad** |
| [`documentos/arquitectura.md`](documentos/arquitectura.md) | Cómo está armado y por qué |
| [`documentos/decisiones/`](documentos/decisiones/) | Decisiones tomadas, con su motivo |
| [`documentos/despliegue.md`](documentos/despliegue.md) | Publicarlo en internet |
| [`CLAUDE.md`](CLAUDE.md) | Restricciones no negociables |

---

## Comandos de operación

Solo si necesitas operar o diagnosticar. Para usar la app, basta el lanzador.

```bash
python -m backend.consola doctor                   # entorno, conectividad, cuota
python -m backend.consola sync-dia 2026-09-04      # sincroniza un día concreto
python -m backend.consola traer 1509-5-L126        # trae una licitación por código
python -m backend.consola capturar-fixture 1509-5-L126
python -m backend.consola run-job                  # lista las tareas programadas
python -m backend.consola importar-procedimientos  # publica los PROCESO.md
python -m backend.consola estado                   # resumen del contenido
pytest                                             # los 79 tests
```

`doctor` es lo primero que hay que correr cuando algo no funciona: la mayoría de
los problemas de este tipo de sistema son de configuración, no de lógica.

---

## Cómo agregar un módulo

1. Crear `backend/modulos/mN_nombre/` con la anatomía descrita en
   [`CLAUDE.md`](CLAUDE.md) §5.
2. Exponer un `MODULO: Modulo` en su `__init__.py`.
3. Añadirlo a `_MANIFIESTOS` en `backend/modulos/__init__.py`.

No hay paso 4. **Si tuviste que tocar `nucleo/` o `app.py`, el diseño falló** — y
hay tests de arquitectura que lo detectan.

Los módulos no se importan entre sí: se comunican por el bus de eventos
(`backend/nucleo/eventos.py`). Ver [`documentos/arquitectura.md`](documentos/arquitectura.md) §2.

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

## Estado

Fase 1 en construcción. M0 y M1 operativos y verificados contra la API real;
M2–M11 declarados en el registro con su estado real, visible en `/sistema/modulos`.

Lo que bloquea el avance está en la portada de la aplicación y en
[`documentos/ESTADO.md`](documentos/ESTADO.md).
