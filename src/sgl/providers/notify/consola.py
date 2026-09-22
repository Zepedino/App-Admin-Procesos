"""Notificador de consola: registra en el log en vez de enviar.

Es el canal por defecto en desarrollo y la red de seguridad en produccion: si
ningun canal real esta configurado, la alerta igual queda registrada. Una alerta
que no se envio y ademas no se registro es una alerta que se perdio.
"""

from __future__ import annotations

from sgl.core.logging import obtener_logger
from sgl.providers.notify.base import CanalNotificacion, Mensaje, NotifyProvider

log = obtener_logger("sgl.notificaciones")


class NotificadorConsola(NotifyProvider):
    nombre = "consola"
    canal = CanalNotificacion.CONSOLA

    def acepta(self, mensaje: Mensaje) -> bool:
        return True  # la consola recibe todo

    def enviar(self, mensaje: Mensaje) -> bool:
        log.info(
            mensaje.asunto,
            extra={
                "canal": "consola",
                "urgencia": mensaje.urgencia.etiqueta,
                "destinatarios": ",".join(mensaje.destinatarios) or "-",
                "entidad": mensaje.entidad,
                "enlace": mensaje.enlace,
                "cuerpo": mensaje.cuerpo[:400],
            },
        )
        return True
