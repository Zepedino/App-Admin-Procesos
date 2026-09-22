"""Tests del adaptador de Mercado Publico, contra respuestas REALES guardadas.

No se toca la red. Los fixtures son la respuesta literal de la API, así que si
ChileCompra cambia el contrato, estos tests siguen pasando y el sistema falla en
produccion: por eso el adaptador ademas lanza RespuestaInesperada, que es la
señal visible de que el contrato cambio (riesgo del PRD seccion 9).
"""

from __future__ import annotations

from datetime import date

import pytest

from sgl.providers.procurement.base import (
    EstadoLicitacion,
    LicitacionDetalle,
    NaturalezaMonto,
    TipoLicitacion,
)
from sgl.providers.procurement.fixture import ProveedorFixture

# --- Mapeo del detalle real --------------------------------------------------


def test_campos_clave_del_detalle_real(detalle_real):
    """Los campos que el PRD seccion 4.1 marca como clave para el scoring."""
    d = LicitacionDetalle.desde_api(detalle_real)

    assert d.codigo == "425-57-LR26"
    assert d.tipo is TipoLicitacion.LR
    assert d.estado is EstadoLicitacion.PUBLICADA
    assert d.estado.es_activa

    assert d.comprador.codigo_organismo == "7342"
    assert d.comprador.region_unidad.startswith("Regi")

    # Banderas: la API las entrega como texto "0"/"1", no como booleanos.
    assert d.obras is False
    assert d.toma_razon is False
    assert d.subcontratacion is False
    assert d.extension_plazo is True   # viene como 1

    assert d.naturaleza_monto is NaturalezaMonto.PRESUPUESTO_DISPONIBLE
    assert d.monto_estimado is None    # VisibilidadMonto=0 en el dato real
    assert d.tipo_pago == "4"


def test_fechas_se_interpretan_como_hora_de_chile(detalle_real):
    """La API entrega ISO sin offset. Es hora de Chile y se guarda en UTC.

    Mezclar esto es la fuente numero uno de errores de fecha, y aqui las fechas
    son plazos legales.
    """
    d = LicitacionDetalle.desde_api(detalle_real)

    assert d.fechas.cierre is not None
    assert d.fechas.cierre.tzinfo is not None
    assert d.fechas.cierre.utcoffset().total_seconds() == 0  # almacenado en UTC

    from sgl.core.tiempo import a_local

    local = a_local(d.fechas.cierre)
    # En el JSON real: "FechaCierre": "2026-11-13T15:00:00"
    assert (local.year, local.month, local.day, local.hour) == (2026, 11, 13, 15)


def test_fechas_del_foro_no_se_confunden_con_vigencia(detalle_real):
    """Dentro del bloque Fechas, FechaInicio/FechaFinal son el periodo de preguntas."""
    d = LicitacionDetalle.desde_api(detalle_real)
    assert d.fechas.fin_preguntas is not None
    assert d.fechas.publicacion_respuestas is not None
    assert d.fechas.fin_preguntas < d.fechas.cierre


def test_items_y_categorias_unspsc(detalle_real):
    d = LicitacionDetalle.desde_api(detalle_real)
    assert len(d.items) == 1
    assert d.categorias_unspsc == {"72131500"}
    assert "inspecci" in d.texto_busqueda.lower()


def test_json_crudo_se_conserva_completo(detalle_real):
    """Permite reprocesar sin gastar cuota cuando falte un campo que hoy no mapeamos."""
    d = LicitacionDetalle.desde_api(detalle_real)
    assert d.crudo == detalle_real
    assert "CantidadReclamos" in d.crudo


# --- Estados -----------------------------------------------------------------


@pytest.mark.parametrize(
    "codigo,esperado,activa",
    [
        (5, "Publicada", True),
        (6, "Cerrada", False),
        (7, "Desierta", False),
        (8, "Adjudicada", False),
        (18, "Revocada", False),
        (19, "Suspendida", False),
    ],
)
def test_estados_del_prd(codigo, esperado, activa):
    estado = EstadoLicitacion.desde_codigo(codigo)
    assert estado.etiqueta == esperado
    assert estado.es_activa is activa


def test_estado_desconocido_no_revienta():
    assert EstadoLicitacion.desde_codigo(999) is None
    assert EstadoLicitacion.desde_codigo(None) is None


# --- Proveedor de fixtures ---------------------------------------------------


def test_fixture_devuelve_el_listado_real():
    proveedor = ProveedorFixture()
    listado = proveedor.licitaciones_del_dia(date(2026, 9, 4))
    assert len(listado) == 1214
    assert not proveedor.en_vivo


def test_fixture_no_inventa_cuando_falta(caplog):
    """Devolver vacio y avisar. Un dato inventado en una decision de negocio es peor."""
    proveedor = ProveedorFixture()
    assert proveedor.detalle("9999-99-XX99") is None
    assert proveedor.licitaciones_del_dia(date(1999, 1, 1)) == []
    assert proveedor.fixtures_faltantes()


def test_fixture_no_consume_cuota():
    estado = ProveedorFixture().estado_cuota()
    assert estado.usadas == 0
    assert not estado.degradado
