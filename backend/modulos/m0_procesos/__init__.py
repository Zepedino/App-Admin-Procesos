"""M0 - Procesos documentados (transversal, desde el dia 1)."""

from __future__ import annotations

from backend.modulos.m0_procesos.routes import router
from backend.nucleo.registro import EstadoModulo, Modulo

MODULO = Modulo(
    id="m0_procesos",
    nombre="Procesos documentados",
    descripcion=(
        "Procedimientos versionados accesibles desde cada pantalla, responsables y SLA "
        "por estado del ciclo de vida, y la revision de los viernes como vista del sistema."
    ),
    fase=0,
    estado=EstadoModulo.PARCIAL,
    requisitos=("RF-0.1", "RF-0.2", "RF-0.3", "RF-0.4"),
    router=router,
    notas=(
        "Aborda el hallazgo 1, del que dependen varios de los demas. "
        "Pendiente: editor de procedimientos en la UI y seguimiento de cambios normativos."
    ),
)

__all__ = ["MODULO"]
