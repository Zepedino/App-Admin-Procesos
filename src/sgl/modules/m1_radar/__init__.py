"""M1 - Radar de oportunidades.

Manifiesto del modulo. Ver PROCESO.md para el procedimiento operativo (M0).
"""

from __future__ import annotations

from sgl.core.registro import EstadoModulo, Modulo
from sgl.modules.m1_radar.jobs import registrar_jobs, registrar_suscripciones
from sgl.modules.m1_radar.routes import router

MODULO = Modulo(
    id="m1_radar",
    nombre="Radar de oportunidades",
    descripcion=(
        "Sincroniza licitaciones desde Mercado Publico, las filtra contra el perfil "
        "de interes configurable, deduplica, detecta cambios y adendas, y ofrece la "
        "bandeja del dia."
    ),
    fase=1,
    estado=EstadoModulo.PARCIAL,
    requisitos=("RF-1.1", "RF-1.2", "RF-1.3", "RF-1.4", "RF-1.5", "RF-1.6"),
    router=router,
    registrar_jobs=registrar_jobs,
    registrar_suscripciones=registrar_suscripciones,
    notas=(
        "Construido y verificado contra la API real. Pendiente: geocodificacion para "
        "el criterio de distancia y el enganche con M2 al marcar 'interesa'."
    ),
)

__all__ = ["MODULO"]
