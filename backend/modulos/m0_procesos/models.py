"""Modelos de M0 - Procesos documentados.

Hallazgo 1 del levantamiento: "Desconocimiento de los procesos. No hay claridad
interna sobre como operan los procesos propios; no estan formalizados."

Varios de los otros hallazgos son sintomas de este. Por eso M0 es transversal y
existe desde el dia 1, no como una fase posterior.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum

from sqlalchemy import Boolean, Date, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.nucleo.auditoria import Auditable
from backend.nucleo.modelo_base import FechaHoraUTC, ModeloBase


class EstadoProcedimiento(StrEnum):
    BORRADOR = "borrador"
    VIGENTE = "vigente"
    OBSOLETO = "obsoleto"


class Procedimiento(ModeloBase, Auditable):
    """PRD seccion 7: Procedimiento.

    RF-0.1: cada flujo tiene un procedimiento escrito, versionado y accesible
    desde la pantalla correspondiente. De ahi `ruta_pantalla`: el documento vive
    junto al trabajo, no en una carpeta que nadie abre.
    """

    __tablename__ = "procedimientos"
    __modulo_auditoria__ = "m0_procesos"

    codigo: Mapped[str] = mapped_column(String(40), unique=True, index=True, nullable=False)
    proceso: Mapped[str] = mapped_column(String(200), nullable=False)
    modulo: Mapped[str | None] = mapped_column(String(40), index=True)
    ruta_pantalla: Mapped[str | None] = mapped_column(String(200))

    version: Mapped[str] = mapped_column(String(20), default="1.0", nullable=False)
    estado: Mapped[str] = mapped_column(
        String(20), default=EstadoProcedimiento.BORRADOR, nullable=False
    )
    responsable: Mapped[str | None] = mapped_column(String(120))
    contenido: Mapped[str | None] = mapped_column(Text)

    ultima_revision: Mapped[date | None] = mapped_column(Date)
    meses_entre_revisiones: Mapped[int] = mapped_column(Integer, default=6, nullable=False)

    versiones: Mapped[list[VersionProcedimiento]] = relationship(
        back_populates="procedimiento", cascade="all, delete-orphan"
    )

    @property
    def dias_desde_revision(self) -> int | None:
        if self.ultima_revision is None:
            return None
        from backend.nucleo.tiempo import ahora_local

        return (ahora_local().date() - self.ultima_revision).days

    @property
    def revision_vencida(self) -> bool:
        """RF-0.3: procedimientos sin revision hace mas de X meses."""
        dias = self.dias_desde_revision
        if dias is None:
            return True
        return dias > self.meses_entre_revisiones * 30

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Procedimiento {self.codigo} v{self.version}>"


class VersionProcedimiento(ModeloBase):
    """RF-0.4: bitacora de cambios de procedimiento.

    Se guarda el contenido completo de cada version, no un diff: recuperar "que
    decia el procedimiento cuando ocurrio el problema" tiene que ser trivial.
    """

    __tablename__ = "versiones_procedimiento"

    procedimiento_id: Mapped[int] = mapped_column(
        ForeignKey("procedimientos.id", ondelete="CASCADE"), nullable=False
    )
    procedimiento: Mapped[Procedimiento] = relationship(back_populates="versiones")

    version: Mapped[str] = mapped_column(String(20), nullable=False)
    contenido: Mapped[str | None] = mapped_column(Text)
    cambio: Mapped[str | None] = mapped_column(Text)
    autor: Mapped[str | None] = mapped_column(String(120))
    fecha: Mapped[datetime] = mapped_column(FechaHoraUTC, nullable=False)


class EstadoCicloVida(ModeloBase):
    """RF-0.2: cada estado del ciclo de vida tiene responsable y SLA en dias.

    Sin esto, "esta en revision" no significa nada: no se sabe de quien es ni
    cuanto lleva ahi.
    """

    __tablename__ = "estados_ciclo_vida"

    clave: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    nombre: Mapped[str] = mapped_column(String(120), nullable=False)
    orden: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rol_responsable: Mapped[str | None] = mapped_column(String(40))
    sla_dias: Mapped[int | None] = mapped_column(Integer)
    descripcion: Mapped[str | None] = mapped_column(Text)
    procedimiento_codigo: Mapped[str | None] = mapped_column(String(40))


class RevisionSemanal(ModeloBase, Auditable):
    """RF-0.3: la revision de los viernes deja de ser una practica difusa.

    Hallazgo 3: "existe la practica, pero no queda claro su alcance ni quien la
    ejecuta". Aqui queda el registro de ejecucion, con responsable y alcance.
    """

    __tablename__ = "revisiones_semanales"
    __modulo_auditoria__ = "m0_procesos"

    fecha: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    responsable: Mapped[str | None] = mapped_column(String(120))
    ejecutada: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    pendientes_vencidos: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    procedimientos_por_revisar: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cambios_normativos: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    observaciones: Mapped[str | None] = mapped_column(Text)
    acuerdos: Mapped[str | None] = mapped_column(Text)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<RevisionSemanal {self.fecha} ejecutada={self.ejecutada}>"
