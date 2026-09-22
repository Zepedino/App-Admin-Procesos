"""Tests de las restricciones no negociables del PRD.

Estas no son reglas de negocio ordinarias: son los limites que, si se rompen,
hacen que el sistema deje de funcionar (cuota agotada) o que se filtren datos
que no deben salir (reglas duras de IA). Por eso tienen sus propios tests.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from backend.nucleo.config import obtener_config
from backend.nucleo.errors import CuotaAgotada, DatoSensibleBloqueado
from backend.nucleo.tiempo import en_ventana_batch

# --- PRD 4.2: cuota diaria ---------------------------------------------------


def test_cuota_se_persiste_y_no_se_regala_al_reiniciar(bd):
    """El contador vive en la base: un reinicio no debe regalar cuota gastada."""
    from backend.conectores.mercado_publico.cuota import ControlDeCuota

    control = ControlDeCuota()
    control.reservar(5)
    otro_proceso = ControlDeCuota()   # simula un reinicio
    assert otro_proceso.estado().usadas == 5


def test_cuota_agotada_corta_la_operacion(bd, monkeypatch):
    """El tope es duro: se lanza excepcion, no se sigue llamando."""
    from backend.conectores.mercado_publico import cuota as modulo_cuota

    cfg = obtener_config()
    monkeypatch.setattr(cfg.mp, "cuota_diaria", 3)
    monkeypatch.setattr(cfg.mp, "umbral_degradacion", 0.8)

    control = modulo_cuota.ControlDeCuota()
    control.reservar(3)
    with pytest.raises(CuotaAgotada):
        control.reservar(1)


def test_degradacion_al_80_por_ciento_emite_evento_una_sola_vez(bd, monkeypatch):
    """PRD 4.2: al 80% degrada y avisa. Si avisa en cada llamada, lo silencian."""
    from backend.conectores.mercado_publico import cuota as modulo_cuota
    from backend.nucleo.eventos import BUS, Eventos

    cfg = obtener_config()
    monkeypatch.setattr(cfg.mp, "cuota_diaria", 10)
    monkeypatch.setattr(cfg.mp, "umbral_degradacion", 0.8)

    recibidos = []
    BUS.suscribir(Eventos.CUOTA_API_EN_UMBRAL, lambda e: recibidos.append(e), etiqueta="test")

    control = modulo_cuota.ControlDeCuota()
    control.reservar(8)
    assert control.en_modo_degradado()
    control.reservar(1)
    control.reservar(1)

    assert len(recibidos) == 1, "el aviso de umbral debe emitirse una sola vez por dia"
    BUS.limpiar()


# --- PRD 4.2: ventana horaria ------------------------------------------------


@pytest.mark.parametrize(
    "hora,dentro",
    [(22, True), (23, True), (0, True), (3, True), (6, True), (7, False), (12, False), (21, False)],
)
def test_ventana_de_carga_masiva_cruza_la_medianoche(hora, dentro):
    momento = datetime(2026, 9, 7, hora, 30, tzinfo=obtener_config().tz)
    assert en_ventana_batch(momento) is dentro


def test_job_nocturno_no_corre_fuera_de_ventana(bd, monkeypatch):
    from backend.modulos.m1_radar import jobs

    monkeypatch.setattr(jobs, "en_ventana_batch", lambda: False)
    resultado = jobs.sincronizacion_nocturna()
    assert resultado["ejecutado"] is False
    assert "ventana" in resultado["motivo"]


# --- PRD 4.4: reglas duras de IA ---------------------------------------------


def test_documento_interno_nunca_va_al_llm():
    """Regla dura 1. Corta la operacion, no advierte."""
    from backend.conectores.ia.base import OrigenDocumento, verificar_documento_publico

    with pytest.raises(DatoSensibleBloqueado):
        verificar_documento_publico(
            "Nomina de trabajadores", OrigenDocumento.INTERNO, referencia="planilla"
        )


def test_se_bloquea_documento_publico_con_datos_personales():
    """Red de seguridad ante el error de clasificacion humana, que va a ocurrir.

    El tier gratuito de Gemini puede usar los datos para entrenar (PRD 4.4).
    """
    from backend.conectores.ia.base import OrigenDocumento, verificar_documento_publico

    with pytest.raises(DatoSensibleBloqueado) as excinfo:
        verificar_documento_publico(
            "Profesional a cargo: RUT 12.345.678-9",
            OrigenDocumento.PORTAL_PUBLICO,
            referencia="bases.pdf",
        )
    assert "rut_persona" in excinfo.value.contexto["hallazgos"]


def test_bases_publicas_normales_pasan():
    from backend.conectores.ia.base import OrigenDocumento, verificar_documento_publico

    verificar_documento_publico(
        "BASES ADMINISTRATIVAS. El plazo de ejecucion sera de 180 dias corridos.",
        OrigenDocumento.PORTAL_PUBLICO,
        referencia="bases.pdf",
    )


def test_el_proveedor_de_ia_no_puede_saltarse_la_guarda():
    """`analizar` es concreto y `_analizar` abstracto, justo para esto."""
    from backend.conectores.ia.base import LLMProvider, OrigenDocumento, SolicitudAnalisis
    from backend.conectores.ia.nulo import ProveedorNulo

    assert "analizar" in vars(LLMProvider)
    assert "_analizar" in LLMProvider.__abstractmethods__

    with pytest.raises(DatoSensibleBloqueado):
        ProveedorNulo().analizar(
            SolicitudAnalisis(
                tarea="resumen_bases",
                texto="cualquier cosa",
                origen=OrigenDocumento.INTERNO,
            )
        )


def test_todo_dato_de_ia_exige_fuente():
    """Regla dura 3: no se puede construir un campo extraido sin su procedencia."""
    from backend.conectores.ia.base import CampoExtraido, FuenteDato

    with pytest.raises(TypeError):
        CampoExtraido(nombre="monto", valor=1000)  # falta `fuente`

    campo = CampoExtraido(
        nombre="monto",
        valor=1000,
        fuente=FuenteDato(documento="bases.pdf", pagina=4, fragmento="$1.000"),
    )
    assert campo.es_de_ia
    campo.corregir(1200, por="daniela@empresa.cl")
    assert not campo.es_de_ia            # corregido por un humano, ya no es de IA
    assert campo.valor_vigente == 1200
    assert campo.corregido_en is not None


# --- PRD RF-2.4: versionado por hash -----------------------------------------


def test_mismo_contenido_no_crea_version_nueva(bd):
    from backend.conectores.archivos.local import StorageLocal

    storage = StorageLocal()
    ruta = "licitaciones/425-57-LR26/anexos/bases.pdf"
    primero = storage.guardar(ruta, b"contenido de las bases")
    repetido = storage.guardar(ruta, b"contenido de las bases")

    assert primero.version == 1
    assert repetido.version == 1
    assert repetido.contenido_identico


def test_contenido_distinto_crea_version_y_marca_el_cambio(bd):
    """Es exactamente el caso de una adenda que modifica las bases (RF-2.4)."""
    from backend.conectores.archivos.local import StorageLocal

    storage = StorageLocal()
    ruta = "licitaciones/425-57-LR26/anexos/bases.pdf"
    storage.guardar(ruta, b"bases originales")
    segundo = storage.guardar(ruta, b"bases con adenda")

    assert segundo.version == 2
    assert segundo.es_nueva_version
    assert storage.leer(ruta) == b"bases con adenda"
    assert storage.leer(ruta, version=1) == b"bases originales"
    assert len(storage.versiones(ruta)) == 2


def test_ruta_con_salto_de_directorio_se_rechaza(bd):
    from backend.conectores.archivos.local import StorageLocal

    with pytest.raises(ValueError):
        StorageLocal().guardar("../../fuera.txt", b"x")


# --- PRD seccion 3: acceso por rol -------------------------------------------


def test_solo_gerencia_ve_remuneraciones_y_rentabilidad():
    """PRD 3: 'Unico que ve costos de personal y rentabilidad'."""
    from backend.nucleo.seguridad import Permiso, Rol, puede

    assert puede(Rol.GERENCIA, Permiso.VER_REMUNERACIONES)
    assert puede(Rol.GERENCIA, Permiso.VER_RENTABILIDAD)
    for rol in (Rol.LICITACIONES, Rol.ITO, Rol.FINANZAS, Rol.ADMIN):
        assert not puede(rol, Permiso.VER_REMUNERACIONES), rol
        assert not puede(rol, Permiso.VER_RENTABILIDAD), rol


def test_solo_gerencia_decide_go_no_go():
    from backend.nucleo.seguridad import Permiso, Rol, puede

    assert puede(Rol.GERENCIA, Permiso.DECIDIR_GO_NO_GO)
    assert not puede(Rol.LICITACIONES, Permiso.DECIDIR_GO_NO_GO)


def test_exigir_permiso_corta_la_operacion():
    from backend.nucleo.errors import PermisoDenegado
    from backend.nucleo.seguridad import Permiso, Rol, exigir

    with pytest.raises(PermisoDenegado):
        exigir(Rol.ITO, Permiso.VER_REMUNERACIONES)
