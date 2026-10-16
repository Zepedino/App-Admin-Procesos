"""Rutas de M1 - Radar de oportunidades.

Server-rendered con Jinja. Las rutas son delgadas a proposito: validan, llaman a
`services` y renderizan. Si una ruta tiene logica de negocio, esta en el lugar
equivocado y no se puede testear sin HTTP.
"""

from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, BackgroundTasks, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.modulos.m1_radar import services
from backend.modulos.m1_radar.models import (
    CambioDetectado,
    EstadoSeguimiento,
    Licitacion,
    MotivoDescarte,
    Organismo,
    PerfilInteres,
)
from backend.nucleo.db import dependencia_sesion
from backend.nucleo.errors import ReglaDeNegocioViolada
from backend.nucleo.logging import obtener_logger
from backend.nucleo.modelo_base import ahora_utc
from backend.nucleo.tiempo import ahora_local, parsear_fecha_mp
from backend.plantillas import plantillas

log = obtener_logger(__name__)

router = APIRouter(tags=["M1 Radar"])


@router.get("/", response_class=HTMLResponse)
def bandeja(request: Request, s: Session = Depends(dependencia_sesion)) -> HTMLResponse:
    """RF-1.6: bandeja del dia. Lo nuevo, lo que cambio, lo que cierra pronto."""
    datos = services.bandeja_del_dia(s)
    return plantillas.TemplateResponse(
        request,
        "paginas/radar_bandeja.html",
        {
            **datos,
            "resumen": services.resumen_radar(s),
            "huecos": services.dias_sin_sincronizar(s),
            "titulo": "Bandeja del dia",
        },
    )


@router.get("/licitaciones", response_class=HTMLResponse)
def listado(
    request: Request,
    estado: str = Query("", description="estado de seguimiento"),
    q: str = Query("", description="texto libre"),
    s: Session = Depends(dependencia_sesion),
) -> HTMLResponse:
    consulta = select(Licitacion)
    if estado:
        consulta = consulta.where(Licitacion.estado_seguimiento == estado)
    if q:
        patron = f"%{q.strip()}%"
        consulta = consulta.where(Licitacion.nombre.ilike(patron))
    consulta = consulta.order_by(
        Licitacion.puntaje_perfil.desc().nullslast(), Licitacion.fecha_cierre.desc().nullslast()
    ).limit(300)

    return plantillas.TemplateResponse(
        request,
        "paginas/radar_listado.html",
        {
            "licitaciones": s.execute(consulta).scalars().all(),
            "estados": list(EstadoSeguimiento),
            "estado_actual": estado,
            "q": q,
            "titulo": "Licitaciones",
        },
    )


@router.get("/licitaciones/{codigo}", response_class=HTMLResponse)
def detalle(
    request: Request, codigo: str, s: Session = Depends(dependencia_sesion)
) -> HTMLResponse:
    licitacion = services._obtener(s, codigo)
    cambios = (
        s.execute(
            select(CambioDetectado)
            .where(CambioDetectado.licitacion_id == licitacion.id)
            .order_by(CambioDetectado.detectado_en.desc())
        )
        .scalars()
        .all()
    )
    return plantillas.TemplateResponse(
        request,
        "paginas/radar_detalle.html",
        {
            "licitacion": licitacion,
            "cambios": cambios,
            "motivos": list(MotivoDescarte),
            "titulo": licitacion.codigo,
        },
    )


@router.post("/licitaciones/{codigo}/interesa")
def accion_interesa(codigo: str, s: Session = Depends(dependencia_sesion)) -> RedirectResponse:
    services.marcar_interesa(s, codigo)
    return RedirectResponse(f"/radar/licitaciones/{codigo}", status_code=303)


@router.post("/licitaciones/{codigo}/descartar", response_model=None)
def accion_descartar(
    request: Request,
    codigo: str,
    motivo: str = Form(...),
    detalle_texto: str = Form(""),
    s: Session = Depends(dependencia_sesion),
) -> HTMLResponse | RedirectResponse:
    try:
        services.descartar(s, codigo, MotivoDescarte(motivo), detalle_texto)
    except (ReglaDeNegocioViolada, ValueError) as exc:
        licitacion = services._obtener(s, codigo)
        return plantillas.TemplateResponse(
            request,
            "paginas/radar_detalle.html",
            {
                "licitacion": licitacion,
                "cambios": [],
                "motivos": list(MotivoDescarte),
                "error": str(exc),
                "titulo": licitacion.codigo,
            },
            status_code=400,
        )
    return RedirectResponse(f"/radar/licitaciones/{codigo}", status_code=303)


@router.post("/importar")
def importar(codigo: str = Form(...)) -> RedirectResponse:
    """RF-5.1 via 2: pegar un codigo y traerla, aunque nunca haya pasado por el radar."""
    licitacion = services.importar_por_codigo(codigo)
    return RedirectResponse(f"/radar/licitaciones/{licitacion.codigo}", status_code=303)


# --- Perfiles de interes (RF-1.2) --------------------------------------------


@router.get("/perfiles", response_class=HTMLResponse)
def perfiles(request: Request, s: Session = Depends(dependencia_sesion)) -> HTMLResponse:
    return plantillas.TemplateResponse(
        request,
        "paginas/radar_perfiles.html",
        {
            "perfiles": s.execute(select(PerfilInteres).order_by(PerfilInteres.nombre))
            .scalars()
            .all(),
            "titulo": "Perfiles de interes",
        },
    )


@router.get("/perfiles/{perfil_id}", response_class=HTMLResponse)
def perfil_editar(
    request: Request, perfil_id: int, s: Session = Depends(dependencia_sesion)
) -> HTMLResponse:
    perfil = s.get(PerfilInteres, perfil_id)
    return plantillas.TemplateResponse(
        request,
        "paginas/radar_perfil_editar.html",
        {"perfil": perfil, "titulo": f"Perfil: {perfil.nombre if perfil else 'no encontrado'}"},
    )


def _lineas(texto: str) -> list[str]:
    """Las listas se editan como una entrada por linea: es lo mas simple de usar."""
    return [linea.strip() for linea in texto.replace(",", "\n").splitlines() if linea.strip()]


@router.post("/perfiles/{perfil_id}")
def perfil_guardar(
    perfil_id: int,
    nombre: str = Form(...),
    activo: bool = Form(False),
    palabras_clave: str = Form(""),
    palabras_excluidas: str = Form(""),
    categorias_unspsc: str = Form(""),
    regiones: str = Form(""),
    tipos_licitacion: str = Form(""),
    monto_minimo: str = Form(""),
    monto_maximo: str = Form(""),
    solo_obras: bool = Form(False),
    umbral_interes: float = Form(0.5),
    s: Session = Depends(dependencia_sesion),
) -> RedirectResponse:
    perfil = s.get(PerfilInteres, perfil_id)
    if perfil is None:
        perfil = PerfilInteres(nombre=nombre)
        s.add(perfil)

    perfil.nombre = nombre
    perfil.activo = activo
    perfil.palabras_clave = _lineas(palabras_clave)
    perfil.palabras_excluidas = _lineas(palabras_excluidas)
    perfil.categorias_unspsc = _lineas(categorias_unspsc)
    perfil.regiones = _lineas(regiones)
    perfil.tipos_licitacion = _lineas(tipos_licitacion)
    perfil.monto_minimo = float(monto_minimo) if monto_minimo.strip() else None
    perfil.monto_maximo = float(monto_maximo) if monto_maximo.strip() else None
    perfil.solo_obras = solo_obras
    perfil.umbral_interes = umbral_interes
    s.flush()
    return RedirectResponse("/radar/perfiles", status_code=303)


# --- Organismos (lista negra, hallazgo 8) ------------------------------------


@router.get("/organismos", response_class=HTMLResponse)
def organismos(request: Request, s: Session = Depends(dependencia_sesion)) -> HTMLResponse:
    return plantillas.TemplateResponse(
        request,
        "paginas/radar_organismos.html",
        {
            "organismos": s.execute(
                select(Organismo).order_by(Organismo.lista_negra.desc(), Organismo.nombre)
            )
            .scalars()
            .all(),
            "titulo": "Organismos",
        },
    )


@router.post("/organismos/{organismo_id}/lista-negra")
def organismo_lista_negra(
    organismo_id: int,
    motivo: str = Form(...),
    s: Session = Depends(dependencia_sesion),
) -> RedirectResponse:
    """Hallazgo 8: excluir un organismo exige motivo escrito. Queda auditado."""
    organismo = s.get(Organismo, organismo_id)
    if organismo is not None:
        organismo.lista_negra = not organismo.lista_negra
        organismo.motivo_lista_negra = motivo.strip() or None
    return RedirectResponse("/radar/organismos", status_code=303)


# --- Diagnostico y operacion manual ------------------------------------------


@router.get("/sincronizaciones", response_class=HTMLResponse)
def sincronizaciones(request: Request, s: Session = Depends(dependencia_sesion)) -> HTMLResponse:
    from backend.modulos.m1_radar.models import SincronizacionDia

    return plantillas.TemplateResponse(
        request,
        "paginas/radar_sincronizaciones.html",
        {
            "sincronizaciones": s.execute(
                select(SincronizacionDia).order_by(SincronizacionDia.dia.desc()).limit(60)
            )
            .scalars()
            .all(),
            "huecos": services.dias_sin_sincronizar(s),
            "estadisticas_descarte": services.estadisticas_descarte(s),
            "titulo": "Sincronizaciones",
        },
    )


@router.post("/sincronizar")
def sincronizar_manual(
    tareas: BackgroundTasks, dia: str = Form("")
) -> RedirectResponse:
    """Sincronizacion a peticion. Util para reponer un dia que fallo.

    Corre en SEGUNDO PLANO y redirige de inmediato. Antes se ejecutaba dentro
    de la peticion, y como el adaptador espera 3 segundos entre llamadas para
    no gatillar el HTTP 429, un dia con varias candidatas dejaba el navegador
    cargando mas de un minuto sin dar senal de vida. Parecia que la aplicacion
    se habia colgado, y lo normal entonces es recargar la pagina y disparar una
    segunda sincronizacion encima de la primera.

    El resultado aparece en /radar/sincronizaciones cuando termina.
    """
    objetivo: date
    if dia.strip():
        try:
            objetivo = date.fromisoformat(dia.strip())
        except ValueError:
            objetivo = parsear_fecha_mp(dia.strip())
    else:
        objetivo = ahora_local().date() - timedelta(days=1)

    tareas.add_task(_sincronizar_en_segundo_plano, objetivo)
    return RedirectResponse("/radar/sincronizaciones?lanzada=1", status_code=303)


def _sincronizar_en_segundo_plano(objetivo: date) -> None:
    """Envoltorio con bitacora: una tarea de fondo que falla en silencio es
    peor que una lenta (PRD seccion 6)."""
    try:
        resultado = services.sincronizar_dia(objetivo, limite_detalles=50)
        log.info("sincronizacion manual terminada", extra=resultado.a_dict())
    except Exception:
        log.exception("sincronizacion manual fallo", extra={"dia": objetivo.isoformat()})


@router.post("/cambios/{cambio_id}/visto")
def marcar_cambio_visto(
    cambio_id: int, s: Session = Depends(dependencia_sesion)
) -> RedirectResponse:
    """RF-10.4: una alerta se cierra con una accion. Las que nadie cierra son ruido."""
    from backend.nucleo.contexto import actor_o_sistema

    cambio = s.get(CambioDetectado, cambio_id)
    if cambio is not None:
        cambio.visto_por = actor_o_sistema().identificador
        cambio.visto_en = ahora_utc()
    return RedirectResponse("/radar/", status_code=303)
