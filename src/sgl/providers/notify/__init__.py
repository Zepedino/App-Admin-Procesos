"""Envío de notificaciones. Punto único: `obtener_notificador()`."""

from __future__ import annotations

import functools

from sgl.core.config import obtener_config
from sgl.providers.notify.base import (
    CanalNotificacion,
    Mensaje,
    NotifyProvider,
    Urgencia,
)
from sgl.providers.notify.compuesto import NotificadorCompuesto

__all__ = [
    "CanalNotificacion",
    "Mensaje",
    "NotifyProvider",
    "Urgencia",
    "obtener_notificador",
    "reiniciar_notificador",
]


@functools.lru_cache(maxsize=1)
def obtener_notificador() -> NotifyProvider:
    cfg = obtener_config()
    canales: list[NotifyProvider] = []
    for nombre in cfg.notificaciones.backends_lista:
        if nombre == "consola":
            from sgl.providers.notify.consola import NotificadorConsola

            canales.append(NotificadorConsola())
        elif nombre == "email":
            from sgl.providers.notify.correo import NotificadorCorreo

            canales.append(NotificadorCorreo())
    if not canales:
        from sgl.providers.notify.consola import NotificadorConsola

        canales.append(NotificadorConsola())
    return NotificadorCompuesto(canales)


def reiniciar_notificador() -> None:
    obtener_notificador.cache_clear()
