"""Rutas de M0 - Procesos documentados."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from sgl.core.db import dependencia_sesion
from sgl.core.tiempo import ahora_local
from sgl.modules.m0_procesos import services
from sgl.modules.m0_procesos.models import EstadoCicloVida, Procedimiento, RevisionSemanal
from sgl.web import plantillas

router = APIRouter(tags=["M0 Procesos"])


@router.get("/", response_class=HTMLResponse)
def listado(request: Request, s: Session = Depends(dependencia_sesion)) -> HTMLResponse:
    return plantillas.TemplateResponse(
        request,
        "pages/procesos_listado.html",
        {
            "procedimientos": s.execute(
                select(Procedimiento).order_by(Procedimiento.codigo)
            ).scalars().all(),
            "por_revisar": services.procedimientos_por_revisar(s),
            "estados_ciclo": s.execute(
                select(EstadoCicloVida).order_by(EstadoCicloVida.orden)
            ).scalars().all(),
            "titulo": "Procesos documentados",
        },
    )


@router.get("/revision-semanal", response_class=HTMLResponse)
def revision_semanal(request: Request, s: Session = Depends(dependencia_sesion)) -> HTMLResponse:
    """RF-0.3: la revision de los viernes, como vista del sistema."""
    revision = services.preparar_revision_semanal(s)
    return plantillas.TemplateResponse(
        request,
        "pages/procesos_revision.html",
        {
            "revision": revision,
            "por_revisar": services.procedimientos_por_revisar(s),
            "historial": s.execute(
                select(RevisionSemanal).order_by(RevisionSemanal.fecha.desc()).limit(20)
            ).scalars().all(),
            "titulo": "Revision semanal",
        },
    )


@router.post("/revision-semanal")
def registrar_revision(
    responsable: str = Form(...),
    observaciones: str = Form(""),
    acuerdos: str = Form(""),
    s: Session = Depends(dependencia_sesion),
) -> RedirectResponse:
    revision = services.preparar_revision_semanal(s, ahora_local().date())
    revision.responsable = responsable
    revision.observaciones = observaciones or None
    revision.acuerdos = acuerdos or None
    revision.ejecutada = True
    return RedirectResponse("/procesos/revision-semanal", status_code=303)


@router.get("/{codigo}", response_class=HTMLResponse)
def detalle(
    request: Request, codigo: str, s: Session = Depends(dependencia_sesion)
) -> HTMLResponse:
    procedimiento = s.execute(
        select(Procedimiento).where(Procedimiento.codigo == codigo)
    ).scalar_one_or_none()
    return plantillas.TemplateResponse(
        request,
        "pages/procesos_detalle.html",
        {"procedimiento": procedimiento, "titulo": f"Procedimiento {codigo}"},
    )
