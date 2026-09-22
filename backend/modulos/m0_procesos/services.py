"""Servicios de M0 - Procesos documentados."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.modulos.m0_procesos.models import (
    EstadoProcedimiento,
    Procedimiento,
    RevisionSemanal,
    VersionProcedimiento,
)
from backend.nucleo.contexto import actor_o_sistema
from backend.nucleo.db import sesion
from backend.nucleo.logging import obtener_logger
from backend.nucleo.modelo_base import ahora_utc
from backend.nucleo.tiempo import ahora_local

log = obtener_logger(__name__)


def guardar_version(s: Session, procedimiento: Procedimiento, cambio: str) -> VersionProcedimiento:
    """RF-0.4: cada modificacion deja una version completa."""
    version = VersionProcedimiento(
        procedimiento_id=procedimiento.id,
        version=procedimiento.version,
        contenido=procedimiento.contenido,
        cambio=cambio,
        autor=actor_o_sistema().identificador,
        fecha=ahora_utc(),
    )
    s.add(version)
    return version


def procedimientos_por_revisar(s: Session) -> list[Procedimiento]:
    """RF-0.3: procedimientos sin revision hace mas de X meses."""
    todos = s.execute(
        select(Procedimiento).where(Procedimiento.estado == EstadoProcedimiento.VIGENTE)
    ).scalars().all()
    return [p for p in todos if p.revision_vencida]


def preparar_revision_semanal(s: Session, fecha: date | None = None) -> RevisionSemanal:
    """RF-0.3: convierte la revision de los viernes en una vista del sistema.

    Junta lo que hay que mirar: pendientes vencidos, procedimientos sin revisar
    y cambios normativos por revisar. Deja registro de ejecucion con responsable.
    """
    objetivo = fecha or ahora_local().date()
    revision = s.execute(
        select(RevisionSemanal).where(RevisionSemanal.fecha == objetivo)
    ).scalar_one_or_none()
    if revision is None:
        revision = RevisionSemanal(fecha=objetivo)
        s.add(revision)

    revision.procedimientos_por_revisar = len(procedimientos_por_revisar(s))
    revision.pendientes_vencidos = _contar_pendientes_vencidos(s)
    s.flush()
    return revision


def _contar_pendientes_vencidos(s: Session) -> int:
    """Pendientes vencidos a lo largo del sistema.

    M0 NO importa los demas modulos: pregunta al registro del nucleo
    (`core/pendientes.py`), donde cada modulo inscribe su propio contador.
    Cuando se construya M7, sus plazos de descargos vencidos apareceran aqui
    sin tocar una linea de este archivo.
    """
    from backend.nucleo.pendientes import total_pendientes

    return total_pendientes()


def detalle_pendientes_vencidos() -> list[tuple[str, int, str]]:
    """Desglose por fuente, para que la revision del viernes sepa donde mirar."""
    from backend.nucleo.pendientes import detalle_pendientes

    return [(f.etiqueta, total, f.ruta) for f, total in detalle_pendientes() if total]


def importar_desde_paquetes(raiz_modulos: Path) -> dict:
    """Carga los PROCESO.md de cada modulo a la base de datos (RF-0.1).

    El procedimiento vive junto al codigo, que es donde se mantiene actualizado.
    Este comando lo hace visible desde la pantalla correspondiente, que es lo que
    exige RF-0.1: el documento tiene que estar donde se hace el trabajo, no en
    una carpeta que nadie abre.

    Si el contenido cambio, se guarda la version anterior en la bitacora (RF-0.4).
    """
    resumen = {"creados": 0, "actualizados": 0, "sin_cambios": 0, "archivos": []}

    for archivo in sorted(raiz_modulos.glob("*/PROCESO.md")):
        id_modulo = archivo.parent.name
        contenido = archivo.read_text(encoding="utf-8")
        metadatos = _leer_encabezado(contenido)
        codigo = _codigo_de_modulo(id_modulo)

        with sesion() as s:
            procedimiento = s.execute(
                select(Procedimiento).where(Procedimiento.codigo == codigo)
            ).scalar_one_or_none()

            if procedimiento is None:
                procedimiento = Procedimiento(
                    codigo=codigo,
                    proceso=metadatos.get("titulo", id_modulo),
                    modulo=id_modulo,
                    estado=EstadoProcedimiento.VIGENTE,
                )
                s.add(procedimiento)
                s.flush()
                resumen["creados"] += 1
            elif procedimiento.contenido == contenido:
                resumen["sin_cambios"] += 1
                resumen["archivos"].append(f"{codigo} (sin cambios)")
                continue
            else:
                # RF-0.4: la version anterior no se pierde.
                guardar_version(s, procedimiento, cambio="importado desde PROCESO.md")
                resumen["actualizados"] += 1

            procedimiento.proceso = metadatos.get("titulo", procedimiento.proceso)
            procedimiento.version = metadatos.get("version", procedimiento.version)
            procedimiento.responsable = metadatos.get("responsable")
            procedimiento.ultima_revision = metadatos.get("ultima_revision")
            procedimiento.ruta_pantalla = _ruta_de_modulo(id_modulo)
            procedimiento.contenido = contenido
            resumen["archivos"].append(codigo)

    return resumen


def _codigo_de_modulo(id_modulo: str) -> str:
    """m1_radar -> M1-RADAR. Es el codigo que usan las plantillas."""
    return id_modulo.upper().replace("_", "-", 1).replace("_", "-")


def _ruta_de_modulo(id_modulo: str) -> str:
    return "/" + id_modulo.split("_", 1)[1].replace("_", "-") + "/"


def _leer_encabezado(contenido: str) -> dict:
    """Extrae titulo, version, responsable y ultima revision del encabezado.

    Formato esperado en las dos primeras lineas utiles:

        # Procedimiento — M1 Radar de oportunidades
        **Version:** 1.0 · **Responsable:** Encargado · **Ultima revision:** 2026-09-07
    """
    metadatos: dict = {}
    for linea in contenido.splitlines()[:6]:
        limpia = linea.strip()
        if limpia.startswith("# "):
            metadatos["titulo"] = limpia[2:].replace("Procedimiento — ", "").strip()
        for etiqueta, clave in (
            ("Version:", "version"),
            ("Versión:", "version"),
            ("Responsable:", "responsable"),
            ("Ultima revision:", "ultima_revision"),
            ("Última revisión:", "ultima_revision"),
        ):
            if etiqueta in limpia:
                trozo = limpia.split(etiqueta, 1)[1]
                valor = trozo.split("·")[0].replace("**", "").strip()
                if clave == "ultima_revision":
                    try:
                        metadatos[clave] = date.fromisoformat(valor)
                    except ValueError:
                        pass
                elif valor:
                    metadatos[clave] = valor
    return metadatos
