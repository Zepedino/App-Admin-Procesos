"""Contrato de notificaciones (M10).

RF-10.1: correo siempre; WhatsApp o Telegram para lo urgente.
RF-10.2: preferencias por usuario y tipo de evento, con niveles de urgencia.
         "Sin esto, en una semana silencian todo y el sistema muere."
RF-10.4: toda alerta se cierra con una accion. Las que nadie cierra son ruido.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import IntEnum, StrEnum


class Urgencia(IntEnum):
    """Nivel de una notificacion. Determina por que canales sale."""

    INFORMATIVA = 1   # resumen semanal
    NORMAL = 2        # licitacion nueva que calza con el perfil
    ALTA = 3          # cierra en menos de 48h, documento por vencer
    CRITICA = 4       # plazo de descargos de una multa (RF-7.2)

    @property
    def etiqueta(self) -> str:
        return {1: "Informativa", 2: "Normal", 3: "Alta", 4: "Critica"}[int(self)]


class CanalNotificacion(StrEnum):
    CONSOLA = "consola"
    CORREO = "email"
    WHATSAPP = "whatsapp"
    TELEGRAM = "telegram"
    BANNER = "banner"   # banner permanente en la app, hasta que se cierre


@dataclass(slots=True)
class Mensaje:
    """Una notificacion a enviar."""

    asunto: str
    cuerpo: str
    urgencia: Urgencia = Urgencia.NORMAL
    destinatarios: list[str] = field(default_factory=list)
    enlace: str = ""                   # URL dentro de la app para actuar
    tipo_evento: str = ""              # para las preferencias por usuario (RF-10.2)
    entidad: str = ""                  # 'licitacion:1509-5-L126'
    requiere_cierre: bool = False      # RF-10.4: hay que marcarla como gestionada

    @property
    def canales_sugeridos(self) -> list[CanalNotificacion]:
        """RF-10.1: la gente en terreno no lee correo."""
        if self.urgencia >= Urgencia.CRITICA:
            return [
                CanalNotificacion.CORREO,
                CanalNotificacion.WHATSAPP,
                CanalNotificacion.BANNER,
            ]
        if self.urgencia == Urgencia.ALTA:
            return [CanalNotificacion.CORREO, CanalNotificacion.WHATSAPP]
        return [CanalNotificacion.CORREO]


class NotifyProvider(ABC):
    """Un canal de salida de notificaciones."""

    nombre: str = "abstracto"
    canal: CanalNotificacion = CanalNotificacion.CONSOLA

    @abstractmethod
    def enviar(self, mensaje: Mensaje) -> bool:
        """Envia. Devuelve False si no pudo, sin lanzar: un canal caido no puede
        impedir que los demas entreguen el mensaje."""

    def acepta(self, mensaje: Mensaje) -> bool:
        return self.canal in mensaje.canales_sugeridos
