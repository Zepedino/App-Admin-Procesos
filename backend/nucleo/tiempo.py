"""Utilidades de tiempo y ventanas operativas.

Aisladas aquí porque la ventana 22:00-07:00 y los plazos legales son reglas del
negocio, no detalles: si se calculan mal, se pierde un plazo de descargos.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from backend.nucleo.config import obtener_config
from backend.nucleo.modelo_base import ahora_utc


def ahora_local() -> datetime:
    """Instante actual en la zona configurada (America/Santiago)."""
    return ahora_utc().astimezone(obtener_config().tz)


def a_local(momento: datetime) -> datetime:
    cfg = obtener_config()
    if momento.tzinfo is None:
        momento = momento.replace(tzinfo=cfg.tz)
    return momento.astimezone(cfg.tz)


def en_ventana_batch(momento: datetime | None = None) -> bool:
    """Verdadero si estamos dentro de la ventana de cargas masivas.

    PRD seccion 4.2: cargas masivas recomendadas entre 22:00 y 07:00.
    La ventana cruza la medianoche, por eso la comparacion es disyuntiva.
    """
    cfg = obtener_config().mp
    hora = (momento or ahora_local()).hour
    inicio, fin = cfg.ventana_batch_inicio, cfg.ventana_batch_fin
    if inicio <= fin:
        return inicio <= hora < fin
    return hora >= inicio or hora < fin


def descripcion_ventana_batch() -> str:
    cfg = obtener_config().mp
    return f"{cfg.ventana_batch_inicio:02d}:00-{cfg.ventana_batch_fin:02d}:00"


def formato_fecha_mp(dia: date) -> str:
    """Formato ddmmaaaa que exige el parametro `fecha` de la API."""
    return dia.strftime("%d%m%Y")


def parsear_fecha_mp(texto: str) -> date:
    return datetime.strptime(texto, "%d%m%Y").date()


def parsear_fecha_hora_api(valor: str | None) -> datetime | None:
    """Parsea las fechas ISO sin zona que devuelve la API.

    La API entrega '2026-11-13T15:00:00' sin offset: es hora de Chile.
    Se interpreta como local y se almacena en UTC.
    """
    if not valor:
        return None
    texto = valor.strip()
    if not texto:
        return None
    if texto.endswith("Z"):
        texto = texto[:-1] + "+00:00"
    try:
        momento = datetime.fromisoformat(texto)
    except ValueError:
        return None
    if momento.tzinfo is None:
        momento = momento.replace(tzinfo=obtener_config().tz)
    return momento.astimezone(obtener_utc())


def obtener_utc():
    from datetime import UTC

    return UTC


def dias_habiles_desde(inicio: date, dias: int) -> date:
    """Suma dias habiles (lunes a viernes).

    No considera feriados chilenos: para plazos legales criticos el sistema
    muestra la fecha calculada como estimada y exige confirmacion humana.
    """
    actual = inicio
    restantes = dias
    while restantes > 0:
        actual += timedelta(days=1)
        if actual.weekday() < 5:
            restantes -= 1
    return actual


def dias_hasta(objetivo: datetime | date | None) -> int | None:
    """Dias calendario desde hoy hasta el objetivo. Negativo si ya paso."""
    if objetivo is None:
        return None
    if isinstance(objetivo, datetime):
        objetivo = a_local(objetivo).date()
    return (objetivo - ahora_local().date()).days
