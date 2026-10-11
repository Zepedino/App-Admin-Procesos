"""Fabrica de la aplicacion.

Arma el sistema leyendo el registro de modulos. Agregar un modulo NO requiere
tocar este archivo: si tuviste que editarlo para sumar funcionalidad, el diseno
fallo (ver CLAUDE.md, seccion 5).
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from backend import __version__
from backend.modulos import obtener_registro
from backend.nucleo.auditoria import activar_auditoria_automatica
from backend.nucleo.config import obtener_config
from backend.nucleo.errors import NoEncontrado, PermisoDenegado, SGLError
from backend.nucleo.logging import configurar_logging, obtener_logger
from backend.nucleo.planificador import PLANIFICADOR
from backend.plantillas import DIRECTORIO_ESTATICOS, plantillas, registrar_filtros

log = obtener_logger(__name__)


def _importar_modelos() -> None:
    """Importa todos los modelos para que Alembic y create_all los vean.

    Los modelos viven en sus modulos; sin este import explicito, SQLAlchemy no
    conoce las tablas de un modulo cuyas rutas todavia no se han tocado.
    """
    from backend.conectores.mercado_publico import modelos as _proc  # noqa: F401
    from backend.modulos.m0_procesos import models as _m0  # noqa: F401
    from backend.modulos.m1_radar import models as _m1  # noqa: F401


@asynccontextmanager
async def _ciclo_de_vida(app: FastAPI):
    log.info("aplicacion iniciando", extra={"version": __version__})
    PLANIFICADOR.iniciar()
    try:
        yield
    finally:
        PLANIFICADOR.detener()
        log.info("aplicacion detenida")


def crear_app(*, iniciar_planificador: bool = True) -> FastAPI:
    """Construye la aplicacion. `iniciar_planificador=False` en tests."""
    config = obtener_config()
    configurar_logging(
        nivel=config.log_nivel or ("INFO" if config.es_produccion else "DEBUG"),
        json_salida=config.es_produccion,
    )
    _importar_modelos()
    activar_auditoria_automatica()
    registrar_filtros()

    app = FastAPI(
        title="SGL — Sistema Unico de Gestion de Licitaciones y Contratos",
        description="Consultora ITO / SERVIU. Ver docs/PRD-v1-sistema-licitaciones.md",
        version=__version__,
        lifespan=_ciclo_de_vida if iniciar_planificador else None,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )

    app.mount("/static", StaticFiles(directory=str(DIRECTORIO_ESTATICOS)), name="static")

    _montar_modulos(app)
    _montar_sistema(app)
    _registrar_contexto_global(app)
    _registrar_manejadores_error(app)

    return app


def _montar_modulos(app: FastAPI) -> None:
    """Monta rutas y registra jobs y suscripciones de cada modulo activo."""
    registro = obtener_registro()
    for modulo in registro.activos():
        if modulo.router is not None:
            app.include_router(modulo.router, prefix=modulo.prefijo_url)
            log.info(
                "modulo montado",
                extra={"modulo": modulo.id, "prefijo": modulo.prefijo_url},
            )
        if modulo.registrar_suscripciones is not None:
            modulo.registrar_suscripciones()
        if modulo.registrar_jobs is not None and not PLANIFICADOR.existe(f"{modulo.id}.__marca__"):
            modulo.registrar_jobs(PLANIFICADOR)


def _registrar_contexto_global(app: FastAPI) -> None:
    """Variables presentes en TODA plantilla.

    El aviso de "estos datos no vienen de la API en vivo" y el estado de la cuota
    se inyectan aqui para que ninguna pantalla los pueda omitir por descuido.
    """
    config = obtener_config()

    @app.middleware("http")
    async def _contexto(request: Request, call_next):
        return await call_next(request)

    def procesador_global(request: Request) -> dict:
        from backend.conectores.mercado_publico import obtener_proveedor

        try:
            proveedor = obtener_proveedor()
            cuota = proveedor.estado_cuota()
            en_vivo = proveedor.en_vivo
        except Exception:  # pragma: no cover - la UI no puede caerse por esto
            cuota, en_vivo = None, False

        return {
            "version": __version__,
            "entorno": config.env,
            "ruta_actual": request.url.path,
            "proveedor_en_vivo": en_vivo,
            "ticket_de_pruebas": config.mp.es_ticket_de_pruebas,
            "cuota": cuota,
        }

    plantillas.env.globals["config"] = config
    # Jinja2Templates de FastAPI acepta procesadores de contexto por request.
    plantillas.context_processors.append(procesador_global)


def _montar_sistema(app: FastAPI) -> None:
    """Rutas transversales: inicio, modulos, jobs, auditoria, salud."""
    from fastapi import Depends, Query
    from sqlalchemy import select
    from sqlalchemy.orm import Session

    from backend.nucleo.auditoria import RegistroAuditoria
    from backend.nucleo.db import dependencia_sesion
    from backend.nucleo.tiempo import descripcion_ventana_batch

    @app.get("/", response_class=HTMLResponse)
    def inicio(request: Request, s: Session = Depends(dependencia_sesion)) -> HTMLResponse:
        from backend.modulos.m1_radar.services import resumen_radar

        return plantillas.TemplateResponse(
            request,
            "paginas/inicio.html",
            {
                "resumen": resumen_radar(s),
                "modulos": obtener_registro().modulos,
                "titulo": "Inicio",
            },
        )

    @app.get("/sistema/modulos", response_class=HTMLResponse)
    def modulos(request: Request) -> HTMLResponse:
        registro = obtener_registro()
        return plantillas.TemplateResponse(
            request,
            "paginas/sistema_modulos.html",
            {
                "por_fase": registro.por_fase(),
                "resumen": registro.resumen(),
                "titulo": "Modulos del sistema",
            },
        )

    @app.get("/sistema/jobs", response_class=HTMLResponse)
    def jobs(request: Request) -> HTMLResponse:
        return plantillas.TemplateResponse(
            request,
            "paginas/sistema_jobs.html",
            {
                "jobs": PLANIFICADOR.listar(),
                "planificador_activo": PLANIFICADOR._scheduler is not None,
                "ventana_batch": descripcion_ventana_batch(),
                "titulo": "Tareas programadas",
            },
        )

    @app.get("/sistema/auditoria", response_class=HTMLResponse)
    def auditoria(
        request: Request,
        entidad: str = Query(""),
        actor: str = Query(""),
        s: Session = Depends(dependencia_sesion),
    ) -> HTMLResponse:
        consulta = select(RegistroAuditoria)
        if entidad:
            consulta = consulta.where(RegistroAuditoria.entidad == entidad)
        if actor:
            consulta = consulta.where(RegistroAuditoria.actor.ilike(f"%{actor}%"))
        consulta = consulta.order_by(RegistroAuditoria.ocurrido_en.desc()).limit(300)
        return plantillas.TemplateResponse(
            request,
            "paginas/sistema_auditoria.html",
            {
                "registros": s.execute(consulta).scalars().all(),
                "entidad": entidad,
                "actor": actor,
                "titulo": "Auditoria",
            },
        )

    @app.get("/salud")
    def salud() -> JSONResponse:
        """Para el health check del hosting. No toca la API externa."""
        from sqlalchemy import text

        from backend.nucleo.db import obtener_motor

        try:
            with obtener_motor().connect() as conexion:
                conexion.execute(text("SELECT 1"))
            bd_ok = True
        except Exception as exc:  # pragma: no cover
            log.exception("health check: base de datos inaccesible")
            bd_ok = False
            _ = exc
        return JSONResponse(
            {"ok": bd_ok, "version": __version__, "entorno": obtener_config().env},
            status_code=200 if bd_ok else 503,
        )


def _registrar_manejadores_error(app: FastAPI) -> None:
    """Errores del dominio se muestran; los demas se registran y se avisan."""

    @app.exception_handler(NoEncontrado)
    async def _no_encontrado(request: Request, exc: NoEncontrado):
        return _respuesta_error(request, exc, 404)

    @app.exception_handler(PermisoDenegado)
    async def _permiso(request: Request, exc: PermisoDenegado):
        return _respuesta_error(request, exc, 403)

    @app.exception_handler(SGLError)
    async def _dominio(request: Request, exc: SGLError):
        log.warning(
            "error de dominio",
            extra={"codigo": exc.codigo, "detalle": str(exc), "ruta": request.url.path},
        )
        return _respuesta_error(request, exc, 400)


def _respuesta_error(request: Request, exc: SGLError, codigo_http: int):
    acepta_html = "text/html" in request.headers.get("accept", "")
    if not acepta_html:
        return JSONResponse(
            {"error": exc.codigo, "mensaje": exc.mensaje_usuario, "detalle": str(exc)},
            status_code=codigo_http,
        )
    return plantillas.TemplateResponse(
        request,
        "base/base.html",
        {"titulo": "Error", "error": f"{exc.mensaje_usuario} {exc}"},
        status_code=codigo_http,
    )


app = crear_app()
