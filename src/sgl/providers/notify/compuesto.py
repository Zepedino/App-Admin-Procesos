"""Notificador que reparte un mensaje entre varios canales.

Un canal caido no impide que los demas entreguen. Si NINGUNO logro entregar, se
registra como error explicito: PRD seccion 6, nada falla en silencio.
"""

from __future__ import annotations

from sgl.core.logging import obtener_logger
from sgl.providers.notify.base import Mensaje, NotifyProvider

log = obtener_logger(__name__)


class NotificadorCompuesto(NotifyProvider):
    nombre = "compuesto"

    def __init__(self, canales: list[NotifyProvider]) -> None:
        self._canales = canales

    def acepta(self, mensaje: Mensaje) -> bool:
        return any(c.acepta(mensaje) for c in self._canales)

    def enviar(self, mensaje: Mensaje) -> bool:
        entregados: list[str] = []
        fallidos: list[str] = []

        for canal in self._canales:
            if not canal.acepta(mensaje):
                continue
            try:
                if canal.enviar(mensaje):
                    entregados.append(canal.nombre)
                else:
                    fallidos.append(canal.nombre)
            except Exception:
                fallidos.append(canal.nombre)
                log.exception(
                    "canal de notificacion fallo", extra={"canal": canal.nombre}
                )

        if not entregados:
            log.error(
                "ningun canal pudo entregar la notificacion",
                extra={
                    "asunto": mensaje.asunto,
                    "urgencia": mensaje.urgencia.etiqueta,
                    "fallidos": ",".join(fallidos) or "-",
                },
            )
            return False

        if fallidos:
            log.warning(
                "entrega parcial de notificacion",
                extra={"entregados": ",".join(entregados), "fallidos": ",".join(fallidos)},
            )
        return True

    def canales(self) -> list[str]:
        return [c.nombre for c in self._canales]
