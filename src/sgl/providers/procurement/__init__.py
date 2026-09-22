"""Acceso a datos de compras públicas.

Punto único de entrada: `obtener_proveedor()`. Nadie llama a la API por fuera.
"""

from __future__ import annotations

import functools

from sgl.core.config import obtener_config
from sgl.core.logging import obtener_logger
from sgl.providers.procurement.base import (
    EstadoLicitacion,
    LicitacionDetalle,
    LicitacionResumen,
    ProcurementProvider,
    TipoLicitacion,
)

log = obtener_logger(__name__)

__all__ = [
    "EstadoLicitacion",
    "LicitacionDetalle",
    "LicitacionResumen",
    "ProcurementProvider",
    "TipoLicitacion",
    "obtener_proveedor",
    "reiniciar_proveedor",
]


@functools.lru_cache(maxsize=1)
def obtener_proveedor() -> ProcurementProvider:
    """Devuelve el proveedor configurado.

    Sin `MP_TICKET` cae al proveedor de fixtures, que reproduce respuestas
    REALES guardadas en tests/fixtures/api. Así el sistema es utilizable y
    testeable mientras el ticket de Clave Única está en trámite, y el día que
    llega no cambia una sola línea de lógica de negocio.
    """
    cfg = obtener_config()
    if cfg.mp.hay_ticket:
        from sgl.providers.procurement.mercadopublico import ProveedorMercadoPublico

        log.info("proveedor de compras: API Mercado Público")
        return ProveedorMercadoPublico()

    from sgl.providers.procurement.fixture import ProveedorFixture

    log.warning(
        "proveedor de compras: FIXTURES (sin MP_TICKET). "
        "Los datos provienen de respuestas reales guardadas, no de la API en vivo."
    )
    return ProveedorFixture()


def reiniciar_proveedor() -> None:
    """Solo para tests y para `cli doctor`."""
    obtener_proveedor.cache_clear()
