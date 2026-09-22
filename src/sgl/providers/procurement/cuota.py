"""Contador de cuota diaria de la API (PRD seccion 4.2).

    "10.000 solicitudes/día por ticket, tope no modificable."
    "Si el contador llega al 80% del tope diario, el sistema degrada
     (solo refresca lo que cierra en menos de 48h) y avisa al admin."

Se persiste en base de datos, no en memoria: un reinicio no debe regalar cuota
que ya se gastó. El contador se incrementa ANTES de la llamada, porque una
llamada que falla también consumió cuota del lado de ChileCompra.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import select

from sgl.core.config import obtener_config
from sgl.core.db import sesion
from sgl.core.errors import CuotaAgotada
from sgl.core.eventos import BUS, Eventos
from sgl.core.logging import obtener_logger
from sgl.core.modelo_base import ahora_utc
from sgl.core.tiempo import ahora_local
from sgl.providers.procurement.base import EstadoCuota
from sgl.providers.procurement.modelos import CuotaAPI

log = obtener_logger(__name__)


class ControlDeCuota:
    """Único punto donde se cuenta el consumo del ticket."""

    def _fila_de_hoy(self, s, dia: date) -> CuotaAPI:
        fila = s.execute(select(CuotaAPI).where(CuotaAPI.fecha == dia)).scalar_one_or_none()
        if fila is None:
            fila = CuotaAPI(fecha=dia, llamadas_usadas=0, llamadas_scraper=0)
            s.add(fila)
            s.flush()
        return fila

    def _dia_operativo(self) -> date:
        """El día se cuenta en hora de Chile: es el reloj del tope del ticket."""
        return ahora_local().date()

    def estado(self) -> EstadoCuota:
        cfg = obtener_config().mp
        dia = self._dia_operativo()
        with sesion() as s:
            fila = self._fila_de_hoy(s, dia)
            return EstadoCuota(
                fecha=dia,
                usadas=fila.llamadas_usadas,
                tope=cfg.cuota_diaria,
                umbral=cfg.umbral_llamadas,
                usadas_scraper=fila.llamadas_scraper,
            )

    def reservar(self, cantidad: int = 1, *, es_scraper: bool = False) -> EstadoCuota:
        """Reserva cuota antes de llamar. Lanza CuotaAgotada si no alcanza.

        Devuelve el estado resultante para que el llamador sepa si quedó
        en modo degradado.
        """
        cfg = obtener_config().mp
        dia = self._dia_operativo()

        with sesion() as s:
            fila = self._fila_de_hoy(s, dia)

            if fila.llamadas_usadas + cantidad > cfg.cuota_diaria:
                log.error(
                    "cuota diaria agotada",
                    extra={"usadas": fila.llamadas_usadas, "tope": cfg.cuota_diaria},
                )
                raise CuotaAgotada(
                    "se alcanzó el tope diario de llamadas a Mercado Público",
                    usadas=fila.llamadas_usadas,
                    tope=cfg.cuota_diaria,
                )

            fila.llamadas_usadas += cantidad
            if es_scraper:
                fila.llamadas_scraper += cantidad
            fila.ultima_llamada_en = ahora_utc()

            estado = EstadoCuota(
                fecha=dia,
                usadas=fila.llamadas_usadas,
                tope=cfg.cuota_diaria,
                umbral=cfg.umbral_llamadas,
                usadas_scraper=fila.llamadas_scraper,
            )

            # Avisar una sola vez por día al cruzar el umbral: si avisa en cada
            # llamada, el admin lo silencia y perdemos la señal (RF-10.4).
            if estado.degradado and not fila.aviso_umbral_enviado:
                fila.aviso_umbral_enviado = True
                log.warning(
                    "cuota de API en umbral de degradación",
                    extra={"usadas": estado.usadas, "umbral": estado.umbral},
                )
                BUS.emitir(
                    Eventos.CUOTA_API_EN_UMBRAL,
                    origen="control_de_cuota",
                    usadas=estado.usadas,
                    tope=estado.tope,
                    porcentaje=round(estado.porcentaje, 1),
                )

        return estado

    def hay_disponible(self, cantidad: int = 1) -> bool:
        e = self.estado()
        return e.usadas + cantidad <= e.tope

    def en_modo_degradado(self) -> bool:
        """Con esto activo, el radar solo refresca lo que cierra en menos de 48h."""
        return self.estado().degradado


CUOTA = ControlDeCuota()
