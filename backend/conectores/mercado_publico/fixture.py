"""Proveedor de respaldo que reproduce respuestas REALES guardadas.

No inventa datos. Cada fixture es una respuesta literal de la API de Mercado
Publico, capturada con `sgl capturar-fixture`. Sirve para tres cosas:

1. Trabajar mientras el ticket de Clave Única está en trámite.
2. Tests deterministas que no gastan cuota ni dependen de que el portal esté arriba.
3. Reproducir un bug con exactamente los datos que lo provocaron.

Cuando falta un fixture, este proveedor NO adivina: devuelve vacío y lo registra
de forma visible. Un dato inventado que se cuela a una decisión de negocio es
peor que no tener dato.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from backend.conectores.mercado_publico.base import (
    EstadoCuota,
    EstadoLicitacion,
    LicitacionDetalle,
    LicitacionResumen,
    ProcurementProvider,
)
from backend.nucleo.config import obtener_config
from backend.nucleo.logging import obtener_logger
from backend.nucleo.tiempo import formato_fecha_mp

log = obtener_logger(__name__)

DIRECTORIO_POR_DEFECTO = "pruebas/fixtures/api"


class ProveedorFixture(ProcurementProvider):
    """Lee respuestas guardadas desde disco. No hace red ni consume cuota."""

    nombre = "fixture"
    en_vivo = False

    def __init__(self, directorio: Path | str | None = None) -> None:
        cfg = obtener_config()
        self._dir = Path(directorio) if directorio else cfg.ruta(DIRECTORIO_POR_DEFECTO)
        self._faltantes: set[str] = set()

    # --- Lectura -------------------------------------------------------------

    def _leer(self, nombre: str) -> dict[str, Any] | None:
        ruta = self._dir / f"{nombre}.json"
        if not ruta.exists():
            if nombre not in self._faltantes:
                self._faltantes.add(nombre)
                log.warning(
                    "fixture no encontrado: se devuelve vacío en vez de inventar datos",
                    extra={"fixture": nombre, "directorio": str(self._dir)},
                )
            return None
        try:
            return json.loads(ruta.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            log.exception("fixture ilegible", extra={"fixture": nombre})
            return None

    def _listado(self, nombre: str) -> list[LicitacionResumen]:
        datos = self._leer(nombre)
        if not datos:
            return []
        return [LicitacionResumen.desde_api(x) for x in datos.get("Listado") or []]

    # --- Contrato ProcurementProvider ---------------------------------------

    def licitaciones_del_dia(self, dia: date) -> list[LicitacionResumen]:
        return self._listado(f"licitaciones_fecha_{formato_fecha_mp(dia)}")

    def detalle(self, codigo: str, *, forzar_refresco: bool = False) -> LicitacionDetalle | None:
        datos = self._leer(f"licitacion_{codigo.strip().upper()}")
        listado = (datos or {}).get("Listado") or []
        return LicitacionDetalle.desde_api(listado[0]) if listado else None

    def licitaciones_por_estado(self, estado: EstadoLicitacion) -> list[LicitacionResumen]:
        return self._listado(f"licitaciones_estado_{int(estado)}")

    def licitaciones_por_organismo(self, codigo_organismo: str) -> list[LicitacionResumen]:
        return self._listado(f"licitaciones_organismo_{codigo_organismo}")

    def buscar_organismos(self, texto: str = "") -> list[dict[str, str]]:
        datos = self._leer("compradores")
        lista = (datos or {}).get("listaEmpresas") or []
        salida = [
            {"codigo": str(e.get("CodigoEmpresa", "")), "nombre": str(e.get("NombreEmpresa", ""))}
            for e in lista
        ]
        if texto:
            from backend.nucleo.texto import normalizar

            buscado = normalizar(texto)
            salida = [o for o in salida if buscado in normalizar(o["nombre"])]
        return salida

    def ordenes_de_compra_por_proveedor(self, rut_proveedor: str) -> list[dict[str, Any]]:
        seguro = rut_proveedor.replace(".", "").replace("-", "")
        datos = self._leer(f"ordenes_proveedor_{seguro}")
        return list((datos or {}).get("Listado") or [])

    def estado_cuota(self) -> EstadoCuota:
        """El proveedor de fixtures no consume cuota: siempre reporta cero."""
        cfg = obtener_config().mp
        from backend.nucleo.tiempo import ahora_local

        return EstadoCuota(
            fecha=ahora_local().date(),
            usadas=0,
            tope=cfg.cuota_diaria,
            umbral=cfg.umbral_llamadas,
        )

    # --- Diagnóstico ---------------------------------------------------------

    def fixtures_disponibles(self) -> list[str]:
        if not self._dir.exists():
            return []
        return sorted(p.stem for p in self._dir.glob("*.json"))

    def fixtures_faltantes(self) -> list[str]:
        """Lo que se pidió y no existía. Lo muestra `sgl doctor`."""
        return sorted(self._faltantes)
