"""Jobs de M1 (RF-1.1).

    "Job nocturno (22:00-07:00) que sincroniza licitaciones publicadas.
     Pull liviano cada 4h para las que cierran en menos de 72h."

El horario no es preferencia: el PRD seccion 4.2 dice que las cargas masivas van
entre 22:00 y 07:00 hora de Chile.
"""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select

from backend.conectores.mercado_publico import obtener_proveedor
from backend.modulos.m1_radar.models import EstadoSeguimiento, Licitacion
from backend.modulos.m1_radar.services import sincronizar_dia
from backend.nucleo.db import sesion
from backend.nucleo.eventos import BUS, Eventos
from backend.nucleo.logging import obtener_logger
from backend.nucleo.modelo_base import ahora_utc
from backend.nucleo.tiempo import ahora_local, en_ventana_batch

log = obtener_logger(__name__)

#: Tope de detalles por corrida nocturna. Con 10.000 llamadas diarias y varios
#: jobs compartiendo el ticket, un tope explicito evita que una noche rara
#: (por ejemplo un cambio de perfil demasiado amplio) se coma la cuota.
MAX_DETALLES_POR_NOCHE = 150


def sincronizacion_nocturna() -> dict:
    """Sincroniza el dia anterior y el actual dentro de la ventana permitida."""
    if not en_ventana_batch():
        # No es un error: es la regla. Se registra y se sale.
        log.warning("fuera de la ventana de carga masiva: no se ejecuta")
        return {"ejecutado": False, "motivo": "fuera de ventana 22:00-07:00"}

    hoy = ahora_local().date()
    ayer = hoy - timedelta(days=1)
    salida = {"ejecutado": True, "dias": {}}
    restantes = MAX_DETALLES_POR_NOCHE

    for dia in (ayer, hoy):
        resultado = sincronizar_dia(dia, limite_detalles=restantes)
        restantes = max(0, restantes - resultado.detalles_pedidos)
        salida["dias"][dia.isoformat()] = resultado.a_dict()

    return salida


def pull_liviano_cierres_proximos() -> dict:
    """RF-1.1: cada 4h, refresca solo lo que cierra en menos de 72 horas.

    Es el caso en que una adenda de ultima hora importa de verdad: mover el
    cierre 24 horas antes del cierre cambia todo el plan de la semana.
    """
    proveedor = obtener_proveedor()
    limite = ahora_utc() + timedelta(hours=72)
    revisadas = 0
    cambios = 0

    with sesion() as s:
        codigos = (
            s.execute(
                select(Licitacion.codigo).where(
                    Licitacion.fecha_cierre.is_not(None),
                    Licitacion.fecha_cierre > ahora_utc(),
                    Licitacion.fecha_cierre <= limite,
                    Licitacion.estado_seguimiento.notin_(
                        [EstadoSeguimiento.DESCARTADA, EstadoSeguimiento.PERDIDA]
                    ),
                )
            )
            .scalars()
            .all()
        )

    from backend.modulos.m1_radar.services import guardar_detalle

    for codigo in codigos:
        try:
            detalle = proveedor.detalle(codigo, forzar_refresco=True)
        except Exception as exc:
            log.exception("fallo el refresco de cierre proximo", extra={"codigo": codigo})
            BUS.emitir(
                Eventos.JOB_FALLIDO,
                origen="m1_radar.pull_liviano",
                job_id="m1_radar.pull_liviano",
                error=f"{codigo}: {exc}",
            )
            continue
        if detalle is None:
            continue
        revisadas += 1
        with sesion() as s:
            _, _, diffs = guardar_detalle(s, detalle)
            cambios += len(diffs)

    return {"revisadas": revisadas, "cambios": cambios, "candidatas": len(codigos)}


def avisar_cierres_inminentes() -> dict:
    """Emite un evento por cada licitacion viva que cierra en menos de 48 horas.

    El aviso lo entrega M10; aqui solo se detecta. Separar deteccion de entrega
    permite cambiar los canales sin tocar esta logica.
    """
    limite = ahora_utc() + timedelta(hours=48)
    avisadas = 0

    with sesion() as s:
        proximas = (
            s.execute(
                select(Licitacion).where(
                    Licitacion.fecha_cierre.is_not(None),
                    Licitacion.fecha_cierre > ahora_utc(),
                    Licitacion.fecha_cierre <= limite,
                    Licitacion.estado_seguimiento.in_(
                        [
                            EstadoSeguimiento.NUEVA,
                            EstadoSeguimiento.EN_REVISION,
                            EstadoSeguimiento.INTERESA,
                            EstadoSeguimiento.EN_PREPARACION,
                        ]
                    ),
                )
            )
            .scalars()
            .all()
        )
        for licitacion in proximas:
            BUS.emitir(
                Eventos.LICITACION_CIERRA_PRONTO,
                origen="m1_radar",
                codigo=licitacion.codigo,
                nombre=licitacion.nombre,
                fecha_cierre=licitacion.fecha_cierre,
                estado_seguimiento=licitacion.estado_seguimiento,
            )
            avisadas += 1

    return {"avisadas": avisadas}


def contar_cambios_criticos_sin_revisar() -> int:
    """Cambios criticos que nadie ha cerrado todavia (RF-10.4).

    Se inscribe en el registro del nucleo para que la revision de los viernes
    (RF-0.3) lo cuente sin que M0 tenga que conocer a M1.
    """
    from sqlalchemy import func

    from backend.modulos.m1_radar.models import CambioDetectado

    with sesion() as s:
        return int(
            s.execute(
                select(func.count(CambioDetectado.id)).where(
                    CambioDetectado.visto_en.is_(None),
                    CambioDetectado.critico.is_(True),
                )
            ).scalar_one()
        )


def registrar_suscripciones() -> None:
    """Se llama al montar el modulo. Aqui se declara lo que M1 aporta al resto."""
    from backend.nucleo.pendientes import registrar_contador

    registrar_contador(
        "Cambios criticos de licitaciones sin revisar",
        contar_cambios_criticos_sin_revisar,
        modulo="m1_radar",
        ruta="/radar/",
    )


def registrar_jobs(planificador) -> None:
    """Registra los jobs de M1. Lo llama la fabrica de la aplicacion."""
    planificador.registrar_cron(
        "m1_radar.sincronizacion_nocturna",
        sincronizacion_nocturna,
        descripcion="RF-1.1 Sincronizacion nocturna del radar",
        hora=23,
        minuto=15,
    )
    planificador.registrar_intervalo(
        "m1_radar.pull_liviano",
        pull_liviano_cierres_proximos,
        descripcion="RF-1.1 Refresco de licitaciones que cierran en menos de 72h",
        horas=4,
    )
    planificador.registrar_cron(
        "m1_radar.cierres_inminentes",
        avisar_cierres_inminentes,
        descripcion="Aviso de cierres en menos de 48h",
        hora=8,
        minuto=0,
    )
