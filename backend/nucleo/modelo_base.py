"""Base declarativa y mixins comunes a todas las tablas.

Toda tabla del sistema hereda de `Base`. Los mixins garantizan que las columnas
transversales (timestamps, autoría) existan en todos lados sin repetirlas,
que es lo que hace posible una auditoría uniforme (PRD §6 Trazabilidad).
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime, Integer, String, TypeDecorator, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def ahora_utc() -> datetime:
    """Instante actual en UTC, consciente de zona.

    Todo se guarda en UTC y se presenta en America/Santiago. Mezclar esto es
    la fuente número uno de errores de fecha, y aquí las fechas son plazos legales.
    """
    return datetime.now(UTC)


class FechaHoraUTC(TypeDecorator):
    """DateTime que SIEMPRE entra y sale como UTC con zona horaria.

    Postgres guarda la zona; SQLite no. Sin esto, el mismo instante se guarda
    como aware y se lee como naive, y cualquier comparacion entre lo guardado y
    lo recien traido de la API da "cambio" cuando no lo hubo. En M1 eso significa
    inundar la bandeja de adendas inexistentes; en M5 y M7, calcular mal un plazo.

    Usar SIEMPRE este tipo en vez de DateTime(timezone=True).
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, valor, dialecto):
        if valor is None:
            return None
        if valor.tzinfo is None:
            # Un naive que llega hasta aqui es un error del llamador; asumir UTC
            # es lo unico coherente con `ahora_utc()`.
            return valor.replace(tzinfo=UTC)
        return valor.astimezone(UTC)

    def process_result_value(self, valor, dialecto):
        if valor is None:
            return None
        if valor.tzinfo is None:
            return valor.replace(tzinfo=UTC)
        return valor.astimezone(UTC)


class Base(DeclarativeBase):
    """Base declarativa única. Alembic descubre las tablas desde aquí."""


class IdMixin:
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)


class TimestampMixin:
    creado_en: Mapped[datetime] = mapped_column(
        FechaHoraUTC, default=ahora_utc, server_default=func.now(), nullable=False
    )
    actualizado_en: Mapped[datetime] = mapped_column(
        FechaHoraUTC,
        default=ahora_utc,
        onupdate=ahora_utc,
        server_default=func.now(),
        nullable=False,
    )


class AutoriaMixin:
    """Quién creó y quién modificó por última vez.

    Se llena desde el contexto de request (`core/contexto.py`). Nulo significa
    "lo hizo un job", no "no sabemos".
    """

    creado_por: Mapped[str | None] = mapped_column(String(120), nullable=True)
    actualizado_por: Mapped[str | None] = mapped_column(String(120), nullable=True)


class ModeloBase(Base, IdMixin, TimestampMixin, AutoriaMixin):
    """Modelo estándar: id + timestamps + autoría. Es el que se usa por defecto."""

    __abstract__ = True

    def __repr__(self) -> str:  # pragma: no cover - diagnóstico
        return f"<{type(self).__name__} id={getattr(self, 'id', None)}>"
