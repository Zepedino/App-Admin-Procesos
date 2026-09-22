"""Capa web: plantillas Jinja y filtros de presentacion.

Server-rendered, un solo desplegable. Los filtros viven aqui porque el formato
de fechas y montos es decision de presentacion, no de negocio: en la base todo
se guarda en UTC y en numeros crudos.
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from fastapi.templating import Jinja2Templates

from sgl.core.config import obtener_config

DIRECTORIO_PLANTILLAS = Path(__file__).parent / "templates"
DIRECTORIO_ESTATICOS = Path(__file__).parent / "static"

plantillas = Jinja2Templates(directory=str(DIRECTORIO_PLANTILLAS))


def _local(valor: datetime | None) -> datetime | None:
    if valor is None:
        return None
    cfg = obtener_config()
    if valor.tzinfo is None:
        return valor
    return valor.astimezone(cfg.tz)


def fecha_hora(valor: datetime | None, formato: str = "%d-%m-%Y %H:%M") -> str:
    v = _local(valor)
    return v.strftime(formato) if v else "—"


def fecha_corta(valor: datetime | date | None) -> str:
    if valor is None:
        return "—"
    if isinstance(valor, datetime):
        v = _local(valor)
        return v.strftime("%d-%m-%Y") if v else "—"
    return valor.strftime("%d-%m-%Y")


def monto(valor: float | None, moneda: str = "CLP") -> str:
    """Formato chileno: punto como separador de miles, sin decimales en CLP."""
    if valor is None:
        return "no publicado"
    entero = f"{valor:,.0f}".replace(",", ".")
    return f"${entero}" if moneda == "CLP" else f"{entero} {moneda}"


def cuenta_regresiva(valor: datetime | None) -> str:
    """Cuanto falta para una fecha. Es lo que mira el encargado, no la fecha."""
    if valor is None:
        return "—"
    from sgl.core.modelo_base import ahora_utc

    delta = valor - ahora_utc()
    segundos = delta.total_seconds()
    if segundos < 0:
        return "vencido"
    dias = int(segundos // 86400)
    horas = int((segundos % 86400) // 3600)
    if dias >= 1:
        return f"{dias} d {horas} h"
    minutos = int((segundos % 3600) // 60)
    return f"{horas} h {minutos} min"


def urgencia_cierre(valor: datetime | None) -> str:
    """Clase CSS segun cuanto falta. La urgencia se ve, no se lee."""
    if valor is None:
        return "neutro"
    from sgl.core.modelo_base import ahora_utc

    horas = (valor - ahora_utc()).total_seconds() / 3600
    if horas < 0:
        return "vencido"
    if horas <= 48:
        return "critico"
    if horas <= 168:
        return "atencion"
    return "normal"


def porcentaje(valor: float | None) -> str:
    return f"{valor * 100:.0f}%" if valor is not None else "—"


def lista(valores) -> str:
    return ", ".join(str(v) for v in (valores or [])) or "—"


def registrar_filtros() -> None:
    """Registra los filtros en el entorno Jinja. Lo llama la fabrica de la app."""
    entorno = plantillas.env
    entorno.filters["fecha_hora"] = fecha_hora
    entorno.filters["fecha_corta"] = fecha_corta
    entorno.filters["monto"] = monto
    entorno.filters["cuenta_regresiva"] = cuenta_regresiva
    entorno.filters["urgencia_cierre"] = urgencia_cierre
    entorno.filters["porcentaje"] = porcentaje
    entorno.filters["lista"] = lista
