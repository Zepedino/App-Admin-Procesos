"""Registro de módulos.

Cada módulo del PRD se describe con un `Modulo` que dice qué RF cubre, en qué
fase va, de qué depende y qué expone. El sistema se arma leyendo esta lista.

Beneficio concreto: /sistema/modulos muestra el estado real de la construcción,
y docs/ESTADO.md se genera desde aquí en vez de escribirse a mano y mentir.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum

from fastapi import APIRouter


class EstadoModulo(StrEnum):
    """Honestidad sobre qué está construido de verdad."""

    COMPLETO = "completo"        # implementado y probado contra datos reales
    PARCIAL = "parcial"          # funciona, pero no cubre todos sus RF
    ESQUELETO = "esqueleto"      # contratos y modelos definidos, sin lógica
    PLANIFICADO = "planificado"  # solo existe en el PRD


@dataclass(frozen=True)
class Modulo:
    """Manifiesto de un módulo. Vive en el __init__.py del paquete."""

    id: str                              # ejemplo: m1_radar
    nombre: str                          # Radar de oportunidades
    descripcion: str
    fase: int                            # fase del PRD, seccion 8
    estado: EstadoModulo
    requisitos: tuple[str, ...] = ()     # RF que cubre
    depende_de: tuple[str, ...] = ()     # ids de otros modulos (informativo)
    router: APIRouter | None = None
    registrar_jobs: Callable[[object], None] | None = None
    registrar_suscripciones: Callable[[], None] | None = None
    notas: str = ""

    @property
    def prefijo_url(self) -> str:
        return "/" + self.id.split("_", 1)[1].replace("_", "-")


@dataclass
class RegistroDeModulos:
    """Colección ordenada de módulos activos."""

    modulos: list[Modulo] = field(default_factory=list)

    def registrar(self, modulo: Modulo) -> None:
        if any(m.id == modulo.id for m in self.modulos):
            raise ValueError(f"módulo duplicado: {modulo.id}")
        self.modulos.append(modulo)

    def obtener(self, id_modulo: str) -> Modulo | None:
        return next((m for m in self.modulos if m.id == id_modulo), None)

    def activos(self) -> list[Modulo]:
        """Módulos con algo ejecutable. Los planificados no montan rutas ni jobs."""
        return [m for m in self.modulos if m.estado != EstadoModulo.PLANIFICADO]

    def por_fase(self) -> dict[int, list[Modulo]]:
        salida: dict[int, list[Modulo]] = {}
        for m in sorted(self.modulos, key=lambda x: (x.fase, x.id)):
            salida.setdefault(m.fase, []).append(m)
        return salida

    def resumen(self) -> dict[str, int]:
        conteo = {e.value: 0 for e in EstadoModulo}
        for m in self.modulos:
            conteo[m.estado.value] += 1
        return conteo
