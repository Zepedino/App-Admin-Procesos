"""Tablas propias de la capa de compras públicas: cuota y caché.

Viven en el provider, no en un módulo de negocio, porque son detalle de la
integración: si mañana cambia el proveedor, estas tablas cambian con él.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from sgl.core.modelo_base import Base, FechaHoraUTC, ahora_utc


class CuotaAPI(Base):
    """Consumo diario del ticket (PRD seccion 7: CuotaAPI).

    Una fila por día. Es la única fuente de verdad del consumo: si el proceso se
    reinicia, el contador no se pierde y no se vuelve a gastar cuota ya gastada.
    """

    __tablename__ = "cuota_api"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    fecha: Mapped[date] = mapped_column(Date, nullable=False, unique=True, index=True)
    llamadas_usadas: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    llamadas_scraper: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    ultima_llamada_en: Mapped[datetime | None] = mapped_column(FechaHoraUTC)
    aviso_umbral_enviado: Mapped[bool] = mapped_column(default=False, nullable=False)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<CuotaAPI {self.fecha} {self.llamadas_usadas}>"


class RespuestaCacheada(Base):
    """Caché de respuestas de la API (PRD seccion 6: Caché).

    En base de datos y no en memoria a propósito: sobrevive a reinicios, que es
    justo cuando más caro sale volver a pedir. El JSON crudo se guarda íntegro
    para poder reprocesar sin gastar cuota.
    """

    __tablename__ = "cache_api"
    __table_args__ = (
        UniqueConstraint("clave", name="uq_cache_api_clave"),
        Index("ix_cache_api_expira", "expira_en"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    clave: Mapped[str] = mapped_column(String(300), nullable=False)
    recurso: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    contenido: Mapped[str] = mapped_column(Text, nullable=False)
    obtenido_en: Mapped[datetime] = mapped_column(
        FechaHoraUTC, default=ahora_utc, nullable=False
    )
    expira_en: Mapped[datetime | None] = mapped_column(FechaHoraUTC)
    aciertos: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    @property
    def vigente(self) -> bool:
        return self.expira_en is None or self.expira_en > ahora_utc()

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Cache {self.recurso} {self.clave[:40]}>"


class LlamadaAPI(Base):
    """Bitácora de llamadas. Diagnóstico cuando la API se porta raro.

    La plataforma está etiquetada como beta (PRD seccion 4.2): cuando falle, hay
    que poder responder "¿desde cuándo?" y "¿con qué respondía?" sin adivinar.
    """

    __tablename__ = "llamadas_api"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    momento: Mapped[datetime] = mapped_column(
        FechaHoraUTC, default=ahora_utc, nullable=False, index=True
    )
    recurso: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    parametros: Mapped[str | None] = mapped_column(Text)
    codigo_http: Mapped[int | None] = mapped_column(Integer)
    duracion_ms: Mapped[int | None] = mapped_column(Integer)
    ok: Mapped[bool] = mapped_column(default=True, nullable=False)
    error: Mapped[str | None] = mapped_column(Text)
    intentos: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    desde_cache: Mapped[bool] = mapped_column(default=False, nullable=False)
