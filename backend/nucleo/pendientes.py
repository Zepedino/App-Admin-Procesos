"""Registro de contadores de pendientes vencidos.

Existe por una razon concreta: la revision de los viernes (RF-0.3) necesita
saber cuantos pendientes vencidos hay en TODO el sistema, pero M0 no puede
importar M1, M5, M6 ni M7 para preguntarles (rompe la modularidad, y quitar un
modulo tumbaria M0).

La inversion es la de siempre: M0 pregunta al nucleo, y cada modulo se registra.
Cuando se construya M7, sus plazos de descargos vencidos aparecen en la revision
del viernes sin tocar una linea de M0.

Uso desde un modulo, en su `registrar_suscripciones`:

    from backend.nucleo.pendientes import registrar_contador
    registrar_contador("cambios criticos sin revisar", contar_cambios_sin_ver)
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from backend.nucleo.logging import obtener_logger

log = obtener_logger(__name__)

Contador = Callable[[], int]


@dataclass(frozen=True, slots=True)
class FuenteDePendientes:
    etiqueta: str
    modulo: str
    contar: Contador
    ruta: str = ""      # a donde ir a resolverlos


_FUENTES: list[FuenteDePendientes] = []


def registrar_contador(
    etiqueta: str, contar: Contador, *, modulo: str = "", ruta: str = ""
) -> None:
    if any(f.etiqueta == etiqueta for f in _FUENTES):
        return  # idempotente: registrar dos veces no duplica el conteo
    _FUENTES.append(
        FuenteDePendientes(etiqueta=etiqueta, modulo=modulo, contar=contar, ruta=ruta)
    )
    log.debug("contador de pendientes registrado", extra={"etiqueta": etiqueta})


def detalle_pendientes() -> list[tuple[FuenteDePendientes, int]]:
    """Cuenta cada fuente. Una que falla no impide contar las demas."""
    salida: list[tuple[FuenteDePendientes, int]] = []
    for fuente in _FUENTES:
        try:
            salida.append((fuente, int(fuente.contar())))
        except Exception:
            log.exception(
                "un contador de pendientes fallo", extra={"etiqueta": fuente.etiqueta}
            )
    return salida


def total_pendientes() -> int:
    return sum(total for _, total in detalle_pendientes())


def limpiar() -> None:
    """Solo para tests."""
    _FUENTES.clear()
