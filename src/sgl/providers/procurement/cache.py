"""Caché de respuestas de la API (PRD seccion 6).

    "Detalle de licitación cacheado por código; refrescar solo activas y
     las que cambiaron."

El TTL depende del estado: una licitación Publicada cambia (adendas, aclaraciones,
cambio de fecha de cierre); una Cerrada o Adjudicada es prácticamente inmutable.
Cachear ambas igual sería gastar cuota en lo que no cambia y perderse lo que sí.
"""

from __future__ import annotations

import json
from datetime import timedelta
from typing import Any

from sqlalchemy import delete, select

from sgl.core.config import obtener_config
from sgl.core.db import sesion
from sgl.core.logging import obtener_logger
from sgl.core.modelo_base import ahora_utc
from sgl.providers.procurement.modelos import RespuestaCacheada

log = obtener_logger(__name__)


class CacheRespuestas:
    """Caché persistente en base de datos, con TTL por tipo de recurso."""

    def clave(self, recurso: str, **parametros: Any) -> str:
        partes = "&".join(f"{k}={v}" for k, v in sorted(parametros.items()))
        return f"{recurso}?{partes}"

    def obtener(self, recurso: str, **parametros: Any) -> dict[str, Any] | None:
        """Devuelve el contenido cacheado vigente, o None."""
        clave = self.clave(recurso, **parametros)
        with sesion() as s:
            fila = s.execute(
                select(RespuestaCacheada).where(RespuestaCacheada.clave == clave)
            ).scalar_one_or_none()
            if fila is None or not fila.vigente:
                return None
            fila.aciertos += 1
            try:
                return json.loads(fila.contenido)
            except json.JSONDecodeError:
                log.warning("entrada de caché corrupta, se descarta", extra={"clave": clave})
                return None

    def obtener_vencido(self, recurso: str, **parametros: Any) -> dict[str, Any] | None:
        """Devuelve el contenido aunque esté vencido.

        Se usa como último recurso cuando la API está caída: mostrar un dato de
        ayer marcado como viejo es mejor que mostrar una pantalla en blanco.
        La plataforma es beta y se cae (PRD seccion 4.2).
        """
        clave = self.clave(recurso, **parametros)
        with sesion() as s:
            fila = s.execute(
                select(RespuestaCacheada).where(RespuestaCacheada.clave == clave)
            ).scalar_one_or_none()
            if fila is None:
                return None
            try:
                return json.loads(fila.contenido)
            except json.JSONDecodeError:
                return None

    def guardar(
        self,
        recurso: str,
        contenido: dict[str, Any],
        *,
        ttl: timedelta | None,
        **parametros: Any,
    ) -> None:
        clave = self.clave(recurso, **parametros)
        expira = (ahora_utc() + ttl) if ttl is not None else None
        serializado = json.dumps(contenido, ensure_ascii=False)

        with sesion() as s:
            fila = s.execute(
                select(RespuestaCacheada).where(RespuestaCacheada.clave == clave)
            ).scalar_one_or_none()
            if fila is None:
                s.add(
                    RespuestaCacheada(
                        clave=clave,
                        recurso=recurso,
                        contenido=serializado,
                        expira_en=expira,
                    )
                )
            else:
                fila.contenido = serializado
                fila.obtenido_en = ahora_utc()
                fila.expira_en = expira

    def invalidar(self, recurso: str, **parametros: Any) -> None:
        clave = self.clave(recurso, **parametros)
        with sesion() as s:
            s.execute(delete(RespuestaCacheada).where(RespuestaCacheada.clave == clave))

    def purgar_vencidas(self, *, antiguedad_dias: int = 60) -> int:
        """Borra entradas vencidas y viejas. Job de mantenimiento."""
        corte = ahora_utc() - timedelta(days=antiguedad_dias)
        with sesion() as s:
            resultado = s.execute(
                delete(RespuestaCacheada).where(
                    RespuestaCacheada.expira_en.is_not(None),
                    RespuestaCacheada.expira_en < corte,
                )
            )
            return int(resultado.rowcount or 0)

    def ttl_para_licitacion(self, codigo_estado: int | None) -> timedelta:
        """TTL según el estado. Es la regla que ahorra la mayor parte de la cuota."""
        cfg = obtener_config().mp
        from sgl.providers.procurement.base import EstadoLicitacion

        estado = EstadoLicitacion.desde_codigo(codigo_estado)
        if estado is None or estado.es_activa:
            return timedelta(minutes=cfg.cache_ttl_activas_min)
        return timedelta(days=cfg.cache_ttl_cerradas_dias)


CACHE = CacheRespuestas()
