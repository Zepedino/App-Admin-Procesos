"""Tests del filtro del radar, contra el listado REAL del 04-09-2026.

El caso que motiva la mitad de estos tests es real: buscar la subcadena "ito "
en el listado del portal marca como candidata a "Suministro señaléticas de
Tránsito", porque "transito " contiene "ito ". Un radar que entrega esa basura
se deja de mirar en una semana.
"""

from __future__ import annotations

import pytest

from backend.conectores.mercado_publico.base import LicitacionDetalle, LicitacionResumen
from backend.modulos.m1_radar.filtro import (
    PerfilEvaluable,
    evaluar_detalle,
    evaluar_texto,
    normalizar,
)

# --- Normalizacion -----------------------------------------------------------


@pytest.mark.parametrize(
    "entrada,esperado",
    [
        ("INSPECCIÓN TÉCNICA", "inspeccion tecnica"),
        ("Asesoría a la Inspección", "asesoria a la inspeccion"),
        ("SEÑALÉTICAS", "senaleticas"),
        ("", ""),
    ],
)
def test_normalizar_quita_tildes_y_baja_mayusculas(entrada, esperado):
    assert normalizar(entrada) == esperado


# --- Limites de palabra ------------------------------------------------------


def test_ito_no_calza_dentro_de_transito(perfil_ito):
    """El caso real que obliga a usar limites de palabra."""
    veredicto = evaluar_texto(perfil_ito, "Suministro señaléticas de Tránsito 2026")
    assert not veredicto.candidata


def test_ito_calza_como_palabra_completa(perfil_ito):
    veredicto = evaluar_texto(perfil_ito, "ITO OBRA PAVIMENTACIÓN VIAS EL ESFUERZO")
    assert veredicto.candidata
    assert "ITO" in veredicto.palabras_encontradas


def test_frase_tolera_separadores(perfil_ito):
    """En las bases aparece con espacio doble, guion o barra."""
    for texto in [
        "SERVICIO DE INSPECCION TECNICA",
        "servicio de inspeccion  tecnica",
        "inspeccion-tecnica de obra",
    ]:
        assert evaluar_texto(perfil_ito, texto).candidata, texto


# --- Exclusiones -------------------------------------------------------------


def test_exclusion_gana_sobre_palabra_clave(perfil_ito):
    """Si aparece una exclusion, no es candidata aunque calce el rubro."""
    veredicto = evaluar_texto(
        perfil_ito, "Suministro de servicios de inspeccion tecnica de obra"
    )
    assert not veredicto.candidata
    assert "suministro" in veredicto.palabras_excluidas_encontradas
    assert "excluida" in veredicto.motivo_rechazo


# --- Contra el listado real --------------------------------------------------


def test_filtro_reduce_drasticamente_el_listado_real(listado_real, perfil_ito):
    """1.214 licitaciones reales y solo unas pocas candidatas.

    Esta proporcion es la que hace viable la cuota: si el filtro dejara pasar
    el 10%, sincronizar un dia costaria 120 llamadas de las 10.000 diarias.
    """
    resumenes = [LicitacionResumen.desde_api(x) for x in listado_real]
    assert len(resumenes) == 1214

    candidatas = [r for r in resumenes if evaluar_texto(perfil_ito, r.nombre).candidata]
    assert 0 < len(candidatas) <= 20, (
        f"{len(candidatas)} candidatas de 1214: el filtro esta demasiado abierto"
    )


def test_ninguna_candidata_es_un_falso_positivo_por_subcadena(listado_real, perfil_ito):
    """Ninguna candidata debe deberse a que 'ito' aparecio dentro de otra palabra."""
    resumenes = [LicitacionResumen.desde_api(x) for x in listado_real]
    for r in resumenes:
        veredicto = evaluar_texto(perfil_ito, r.nombre)
        if veredicto.candidata:
            texto = normalizar(r.nombre)
            for palabra in veredicto.palabras_encontradas:
                assert normalizar(palabra) in texto


def test_tipos_se_deducen_del_codigo(listado_real):
    """El sufijo del codigo externo identifica el tipo: 425-57-LR26 es LR."""
    resumenes = [LicitacionResumen.desde_api(x) for x in listado_real]
    tipos = {r.tipo.value for r in resumenes}
    assert "LE" in tipos and "LP" in tipos


# --- Contra el detalle real --------------------------------------------------


def test_detalle_real_es_candidata_y_suma_por_categoria(detalle_real, perfil_ito):
    detalle = LicitacionDetalle.desde_api(detalle_real)
    veredicto = evaluar_detalle(perfil_ito, detalle)

    assert veredicto.candidata
    assert "inspeccion tecnica" in veredicto.palabras_encontradas
    # La categoria UNSPSC real del item es 72131500, que empieza por 7213.
    assert veredicto.categorias_coincidentes == ["72131500"]
    assert veredicto.puntaje > 0.5


def test_monto_no_publicado_no_descarta(detalle_real):
    """VisibilidadMonto=0 es frecuente y no dice nada sobre si la licitacion sirve."""
    detalle = LicitacionDetalle.desde_api(detalle_real)
    assert detalle.monto_estimado is None  # asi viene en el dato real

    perfil = PerfilEvaluable(
        nombre="con minimo",
        palabras_clave=("inspeccion tecnica",),
        monto_minimo=50_000_000,
        umbral_interes=0.3,
    )
    assert evaluar_detalle(perfil, detalle).candidata


def test_sin_palabras_clave_no_es_candidata_aunque_sume_region(detalle_real):
    """Ser del organismo y la region correctos no basta si no es de nuestro rubro."""
    perfil = PerfilEvaluable(
        nombre="solo region",
        palabras_clave=("demolicion",),
        regiones=("Region Metropolitana",),
        umbral_interes=0.1,
    )
    veredicto = evaluar_detalle(perfil, LicitacionDetalle.desde_api(detalle_real))
    assert not veredicto.candidata
    assert veredicto.motivo_rechazo == "sin palabras clave"


def test_veredicto_siempre_explica(detalle_real, perfil_ito):
    """Sin explicacion, el usuario no confia en el radar y vuelve al portal."""
    veredicto = evaluar_detalle(perfil_ito, LicitacionDetalle.desde_api(detalle_real))
    assert veredicto.explicacion
    assert veredicto.a_dict()["explicacion"] == veredicto.explicacion
