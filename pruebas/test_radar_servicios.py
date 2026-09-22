"""Tests de los servicios del radar: deduplicacion, deteccion de cambios,
descarte tipificado y auditoria.

Todo con el detalle REAL de 425-57-LR26.
"""

from __future__ import annotations

import copy
from datetime import date

import pytest
from sqlalchemy import select

from backend.conectores.mercado_publico.base import LicitacionDetalle
from backend.modulos.m1_radar.models import (
    CambioDetectado,
    EstadoSeguimiento,
    Licitacion,
    MotivoDescarte,
    Organismo,
)
from backend.modulos.m1_radar.services import descartar, guardar_detalle, marcar_interesa
from backend.nucleo.contexto import Actor, como
from backend.nucleo.db import sesion
from backend.nucleo.errors import ReglaDeNegocioViolada


@pytest.fixture
def detalle(detalle_real) -> LicitacionDetalle:
    return LicitacionDetalle.desde_api(detalle_real)


def test_guardar_crea_licitacion_y_organismo(bd, detalle):
    with sesion() as s:
        licitacion, es_nueva, cambios = guardar_detalle(s, detalle)
        assert es_nueva
        assert cambios == []
        assert licitacion.codigo == "425-57-LR26"
        assert licitacion.estado_seguimiento == EstadoSeguimiento.NUEVA
        assert licitacion.json_crudo["CodigoExterno"] == "425-57-LR26"

    with sesion() as s:
        assert s.execute(select(Organismo)).scalars().one().codigo_mp == "7342"


def test_no_duplica_al_volver_a_guardar(bd, detalle):
    """RF-1.3: lo ya visto no reaparece como nuevo."""
    with sesion() as s:
        guardar_detalle(s, detalle)
    with sesion() as s:
        _, es_nueva, _ = guardar_detalle(s, detalle)
        assert not es_nueva
    with sesion() as s:
        assert len(s.execute(select(Licitacion)).scalars().all()) == 1


def test_detecta_cambio_de_fecha_de_cierre_como_critico(bd, detalle_real):
    """RF-1.4: mover el cierre es el cambio que mas duele si pasa desapercibido."""
    with sesion() as s:
        guardar_detalle(s, LicitacionDetalle.desde_api(detalle_real))

    modificado = copy.deepcopy(detalle_real)
    modificado["Fechas"]["FechaCierre"] = "2026-11-20T15:00:00"

    with sesion() as s:
        _, es_nueva, cambios = guardar_detalle(s, LicitacionDetalle.desde_api(modificado))
        assert not es_nueva
        campos = {c.campo for c in cambios}
        assert "fecha_cierre" in campos
        assert all(c.critico for c in cambios if c.campo == "fecha_cierre")

    with sesion() as s:
        guardados = s.execute(select(CambioDetectado)).scalars().all()
        assert len(guardados) == 1
        assert "2026-11-20" in guardados[0].valor_nuevo


def test_detecta_cambio_de_monto(bd, detalle_real):
    with sesion() as s:
        guardar_detalle(s, LicitacionDetalle.desde_api(detalle_real))

    modificado = copy.deepcopy(detalle_real)
    modificado["MontoEstimado"] = 85_000_000

    with sesion() as s:
        _, _, cambios = guardar_detalle(s, LicitacionDetalle.desde_api(modificado))
        assert {c.campo for c in cambios} == {"monto_estimado"}


def test_cambio_irrelevante_no_genera_ruido(bd, detalle_real):
    """Si comparamos todo, el ruido entierra la señal y nadie mira las alertas."""
    with sesion() as s:
        guardar_detalle(s, LicitacionDetalle.desde_api(detalle_real))

    modificado = copy.deepcopy(detalle_real)
    modificado["CantidadReclamos"] = 999
    modificado["Comprador"]["NombreUsuario"] = "Otra Persona"

    with sesion() as s:
        _, _, cambios = guardar_detalle(s, LicitacionDetalle.desde_api(modificado))
        assert cambios == []


def test_evento_de_deteccion_se_publica(bd, detalle):
    from backend.nucleo.eventos import BUS, Eventos

    recibidos = []
    BUS.suscribir(Eventos.LICITACION_DETECTADA, lambda e: recibidos.append(e), etiqueta="test")
    with sesion() as s:
        guardar_detalle(s, detalle)
    assert len(recibidos) == 1
    assert recibidos[0].datos["codigo"] == "425-57-LR26"
    BUS.limpiar()


# --- Descarte tipificado (RF-1.5) --------------------------------------------


def test_descarte_exige_motivo_valido_y_deja_registro(bd, detalle):
    with sesion() as s:
        guardar_detalle(s, detalle)

    with como(Actor(identificador="daniela@empresa.cl", nombre="Daniela", rol="gerencia")):
        with sesion() as s:
            licitacion = descartar(
                s, "425-57-LR26", MotivoDescarte.DISTANCIA_EXCESIVA, "obra en Temuco"
            )
            assert licitacion.fue_descartada
            assert licitacion.descartada_por == "daniela@empresa.cl"
            assert licitacion.descartada_en is not None


def test_motivo_otro_exige_explicacion(bd, detalle):
    """Sin explicacion, 'Otro' no sirve para analizar nada en seis meses."""
    with sesion() as s:
        guardar_detalle(s, detalle)
    with sesion() as s:
        with pytest.raises(ReglaDeNegocioViolada):
            descartar(s, "425-57-LR26", MotivoDescarte.OTRO, "   ")


def test_estadisticas_de_descarte_agrupan_por_motivo(bd, detalle_real):
    from backend.modulos.m1_radar.services import estadisticas_descarte

    with sesion() as s:
        for sufijo in ("A", "B", "C"):
            copia = copy.deepcopy(detalle_real)
            copia["CodigoExterno"] = f"425-57-LR2{sufijo}"
            guardar_detalle(s, LicitacionDetalle.desde_api(copia))

    with sesion() as s:
        descartar(s, "425-57-LR2A", MotivoDescarte.SIN_CAPACIDAD)
        descartar(s, "425-57-LR2B", MotivoDescarte.SIN_CAPACIDAD)
        descartar(s, "425-57-LR2C", MotivoDescarte.MONTO_INSUFICIENTE)

    with sesion() as s:
        stats = dict(estadisticas_descarte(s))
        assert stats["sin_capacidad"] == 2
        assert stats["monto_insuficiente"] == 1


# --- Auditoria (PRD seccion 6) -----------------------------------------------


def test_cambio_de_estado_queda_auditado_con_actor(bd, detalle):
    from backend.nucleo.auditoria import RegistroAuditoria

    with sesion() as s:
        guardar_detalle(s, detalle)

    with como(Actor(identificador="daniela@empresa.cl", rol="gerencia")):
        with sesion() as s:
            marcar_interesa(s, "425-57-LR26")

    with sesion() as s:
        registros = s.execute(
            select(RegistroAuditoria).where(RegistroAuditoria.entidad == "Licitacion")
        ).scalars().all()
        acciones = {r.accion for r in registros}
        assert "marcar_interesa" in acciones
        assert any(r.actor == "daniela@empresa.cl" for r in registros)


def test_autoria_se_rellena_desde_el_contexto(bd, detalle):
    with como(Actor(identificador="encargado@empresa.cl", rol="licitaciones")):
        with sesion() as s:
            licitacion, _, _ = guardar_detalle(s, detalle)
            assert licitacion.creado_por == "encargado@empresa.cl"


def test_un_job_queda_identificado_como_tal(bd, detalle):
    from backend.nucleo.contexto import como_job

    with como(como_job("m1_radar.sincronizacion_nocturna")):
        with sesion() as s:
            licitacion, _, _ = guardar_detalle(s, detalle)
            assert licitacion.creado_por.startswith("job:")


# --- Sincronizacion completa con fixtures ------------------------------------


def test_sincronizar_dia_con_datos_reales(bd):
    """Camino completo: 1.214 reales -> filtro -> detalle -> guardado."""
    from backend.modulos.m1_radar.models import PerfilInteres
    from backend.modulos.m1_radar.services import sincronizar_dia
    from backend.nucleo.db import sesion as abrir

    with abrir() as s:
        s.add(
            PerfilInteres(
                nombre="ITO",
                activo=True,
                palabras_clave=["inspeccion tecnica", "ITO", "asesoria a la inspeccion"],
                palabras_excluidas=["suministro", "arriendo"],
                categorias_unspsc=["7213"],
                umbral_interes=0.5,
            )
        )

    resultado = sincronizar_dia(date(2026, 9, 4))

    assert resultado.total_api == 1214
    assert 0 < resultado.candidatas < 20
    # Solo hay un fixture de detalle, asi que solo una se puede guardar entera.
    assert resultado.nuevas >= 1
    assert not resultado.errores


def test_sin_perfiles_no_sincroniza_y_lo_dice(bd):
    """Sin perfil no hay radar. Decirlo, en vez de traer 1.214 detalles."""
    from backend.modulos.m1_radar.services import sincronizar_dia

    resultado = sincronizar_dia(date(2026, 9, 4))
    assert resultado.nuevas == 0
    assert any("perfiles" in e for e in resultado.errores)


def test_auditoria_de_creacion_identifica_la_entidad(bd, detalle):
    """Una fila de auditoria que dice 'se creo algo' sin decir que, no sirve.

    Se prefiere la clave natural (codigo) al id numerico: 'Licitacion
    425-57-LR26' dice algo; 'Licitacion 2' no.
    """
    from backend.nucleo.auditoria import RegistroAuditoria

    with sesion() as s:
        guardar_detalle(s, detalle)

    with sesion() as s:
        creaciones = s.execute(
            select(RegistroAuditoria).where(RegistroAuditoria.accion == "crear")
        ).scalars().all()
        assert creaciones
        assert all(r.entidad_id for r in creaciones), "hay creaciones sin identificar"

        licitacion = next(r for r in creaciones if r.entidad == "Licitacion")
        assert licitacion.entidad_id == "425-57-LR26"

        organismo = next(r for r in creaciones if r.entidad == "Organismo")
        assert organismo.entidad_id == "7342"


def test_importar_procedimientos_es_idempotente_y_versiona(bd):
    """RF-0.1 y RF-0.4: el PROCESO.md de cada modulo llega a la pantalla,
    y una modificacion deja la version anterior en la bitacora."""
    from pathlib import Path

    from backend.modulos.m0_procesos.models import Procedimiento, VersionProcedimiento
    from backend.modulos.m0_procesos.services import importar_desde_paquetes

    raiz = Path(__file__).resolve().parents[1] / "backend" / "modulos"

    primero = importar_desde_paquetes(raiz)
    assert primero["creados"] >= 2

    segundo = importar_desde_paquetes(raiz)
    assert segundo["creados"] == 0
    assert segundo["actualizados"] == 0
    assert segundo["sin_cambios"] >= 2

    with sesion() as s:
        radar = s.execute(
            select(Procedimiento).where(Procedimiento.codigo == "M1-RADAR")
        ).scalar_one()
        assert radar.version == "1.0"
        assert radar.responsable == "Encargado de licitaciones"
        assert radar.ruta_pantalla == "/radar/"
        assert radar.ultima_revision is not None
        assert not radar.revision_vencida

        radar.contenido = "contenido antiguo distinto"

    tercero = importar_desde_paquetes(raiz)
    assert tercero["actualizados"] == 1

    with sesion() as s:
        versiones = s.execute(select(VersionProcedimiento)).scalars().all()
        assert len(versiones) == 1
        assert versiones[0].contenido == "contenido antiguo distinto"
