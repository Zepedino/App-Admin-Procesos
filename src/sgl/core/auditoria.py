"""Bitácora de auditoría (PRD §6 Trazabilidad).

"Auditoría de quién cambió qué, especialmente montos y multas."

Dos mecanismos complementarios:
1. `registrar()` — explícito, para hechos de negocio ("Daniela decidió no postular").
2. `activar_auditoria_automatica()` — engancha el flush de SQLAlchemy y registra
   cambios en las tablas marcadas como auditables. Nadie puede olvidarse de auditar.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Integer, String, Text, event, inspect
from sqlalchemy.orm import Mapped, Session, mapped_column

from sgl.core.contexto import actor_o_sistema
from sgl.core.logging import obtener_logger
from sgl.core.modelo_base import Base, FechaHoraUTC, ahora_utc

log = obtener_logger(__name__)

#: Campos cuyo valor NUNCA se copia a la bitácora (dato sensible o ruido).
CAMPOS_EXCLUIDOS = {"actualizado_en", "creado_en", "actualizado_por", "creado_por"}

#: Campos que exigen registro aunque el modelo no esté marcado como auditable.
CAMPOS_CRITICOS = {
    "monto", "monto_clp", "monto_utm", "monto_final", "monto_estimado",
    "oferta_monto", "costo_hora", "score", "decision", "estado",
}


class RegistroAuditoria(Base):
    """Una fila por cambio. Nunca se edita ni se borra."""

    __tablename__ = "auditoria"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ocurrido_en: Mapped[datetime] = mapped_column(
        FechaHoraUTC, default=ahora_utc, nullable=False, index=True
    )
    actor: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    accion: Mapped[str] = mapped_column(String(40), nullable=False)      # crear|modificar|borrar|<verbo>
    entidad: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    entidad_id: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    campo: Mapped[str | None] = mapped_column(String(80), nullable=True)
    valor_anterior: Mapped[str | None] = mapped_column(Text, nullable=True)
    valor_nuevo: Mapped[str | None] = mapped_column(Text, nullable=True)
    motivo: Mapped[str | None] = mapped_column(Text, nullable=True)
    modulo: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Auditoria {self.accion} {self.entidad}#{self.entidad_id} {self.campo}>"


class Auditable:
    """Marca un modelo para auditoría automática de cambios.

        class Multa(ModeloBase, Auditable):
            __auditar_campos__ = {"monto_clp", "estado"}   # None = todos

    Sin esta marca, el modelo no se audita automáticamente (pero sí se puede
    auditar a mano con `registrar()`).
    """

    __auditar_campos__: set[str] | None = None
    __modulo_auditoria__: str | None = None


def _texto(valor: Any) -> str | None:
    if valor is None:
        return None
    s = str(valor)
    return s if len(s) <= 2000 else s[:1997] + "..."


def registrar(
    sesion: Session,
    *,
    accion: str,
    entidad: str,
    entidad_id: str | int | None = None,
    campo: str | None = None,
    valor_anterior: Any = None,
    valor_nuevo: Any = None,
    motivo: str | None = None,
    modulo: str | None = None,
) -> RegistroAuditoria:
    """Registra un hecho auditable de forma explícita.

    Se usa para decisiones de negocio, no solo para cambios de columna:
    un go/no-go, un descarte con motivo, una alerta cerrada.
    """
    reg = RegistroAuditoria(
        actor=actor_o_sistema().identificador,
        accion=accion,
        entidad=entidad,
        entidad_id=str(entidad_id) if entidad_id is not None else None,
        campo=campo,
        valor_anterior=_texto(valor_anterior),
        valor_nuevo=_texto(valor_nuevo),
        motivo=motivo,
        modulo=modulo,
    )
    sesion.add(reg)
    return reg


def _campos_a_auditar(objeto: Auditable) -> set[str] | None:
    return objeto.__auditar_campos__


#: Nombres de columna que sirven como identificador legible de una entidad.
#: Se prefieren al id numerico: "Licitacion 425-57-LR26" dice algo, "Licitacion 2" no.
CLAVES_NATURALES = ("codigo", "codigo_mp", "clave")


def _identificador(objeto: object) -> str | None:
    for clave in CLAVES_NATURALES:
        valor = getattr(objeto, clave, None)
        if valor:
            return str(valor)
    valor = getattr(objeto, "id", None)
    return str(valor) if valor else None


def _auditar_flush(sesion: Session, _ctx, _instancias) -> None:
    """Se ejecuta antes de cada flush: compara estado previo y nuevo."""
    actor = actor_o_sistema().identificador
    pendientes: list[RegistroAuditoria] = []

    for objeto in sesion.new:
        if not isinstance(objeto, Auditable):
            continue
        registro = RegistroAuditoria(
            actor=actor,
            accion="crear",
            entidad=type(objeto).__name__,
            entidad_id=_identificador(objeto),
            modulo=objeto.__modulo_auditoria__,
        )
        if registro.entidad_id is None:
            # El id autoincremental todavia no existe: se completa en after_flush,
            # cuando la base ya lo asigno. Sin esto, la mitad de la bitacora
            # apuntaria a "algo se creo" sin decir a que.
            _PENDIENTES_DE_ID.append((registro, objeto))
        pendientes.append(registro)

    for objeto in sesion.dirty:
        if not isinstance(objeto, Auditable) or not sesion.is_modified(objeto):
            continue
        estado = inspect(objeto)
        identificador = _identificador(objeto)
        permitidos = _campos_a_auditar(objeto)
        for attr in estado.attrs:
            nombre = attr.key
            if nombre in CAMPOS_EXCLUIDOS:
                continue
            if permitidos is not None and nombre not in permitidos and nombre not in CAMPOS_CRITICOS:
                continue
            historial = attr.load_history()
            if not historial.has_changes():
                continue
            anterior = historial.deleted[0] if historial.deleted else None
            nuevo = historial.added[0] if historial.added else None
            if anterior == nuevo:
                continue
            pendientes.append(
                RegistroAuditoria(
                    actor=actor,
                    accion="modificar",
                    entidad=type(objeto).__name__,
                    entidad_id=identificador,
                    campo=nombre,
                    valor_anterior=_texto(anterior),
                    valor_nuevo=_texto(nuevo),
                    modulo=objeto.__modulo_auditoria__,
                )
            )

    for objeto in sesion.deleted:
        if not isinstance(objeto, Auditable):
            continue
        pendientes.append(
            RegistroAuditoria(
                actor=actor,
                accion="borrar",
                entidad=type(objeto).__name__,
                entidad_id=_identificador(objeto),
                modulo=objeto.__modulo_auditoria__,
            )
        )

    for reg in pendientes:
        sesion.add(reg)


def _rellenar_autoria(sesion: Session, _ctx, _instancias) -> None:
    """Completa creado_por / actualizado_por desde el contexto."""
    actor = actor_o_sistema().identificador
    for objeto in sesion.new:
        if hasattr(objeto, "creado_por") and getattr(objeto, "creado_por", None) is None:
            objeto.creado_por = actor
        if hasattr(objeto, "actualizado_por"):
            objeto.actualizado_por = actor
    for objeto in sesion.dirty:
        if hasattr(objeto, "actualizado_por") and sesion.is_modified(objeto):
            objeto.actualizado_por = actor


#: Registros de creacion que esperan a que la base asigne el id.
_PENDIENTES_DE_ID: list[tuple[RegistroAuditoria, object]] = []


def _completar_ids(sesion: Session, _ctx) -> None:
    """Rellena entidad_id despues del flush, cuando la clave primaria ya existe.

    Mutar aqui deja la fila sucia y `commit()` vuelve a hacer flush hasta que la
    sesion queda limpia, asi que el UPDATE sale solo.
    """
    if not _PENDIENTES_DE_ID:
        return
    pendientes, _PENDIENTES_DE_ID[:] = list(_PENDIENTES_DE_ID), []
    for registro, objeto in pendientes:
        registro.entidad_id = _identificador(objeto)


_activada = False


def activar_auditoria_automatica() -> None:
    """Engancha los listeners globales. Idempotente; se llama al arrancar la app."""
    global _activada
    if _activada:
        return
    event.listen(Session, "before_flush", _rellenar_autoria)
    event.listen(Session, "before_flush", _auditar_flush)
    event.listen(Session, "after_flush", _completar_ids)
    _activada = True
    log.info("auditoría automática activada")
