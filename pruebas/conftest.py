"""Configuracion comun de tests.

Regla: los tests NUNCA tocan la API real ni la base de datos de desarrollo.
Los datos vienen de fixtures capturados de la API real (pruebas/fixtures/api).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
FIXTURES = RAIZ / "pruebas" / "fixtures" / "api"


@pytest.fixture(scope="session", autouse=True)
def _entorno_de_test(tmp_path_factory):
    """Aisla el entorno antes de que se importe cualquier modulo de sgl."""
    directorio = tmp_path_factory.mktemp("sgl_test")
    os.environ["APP_ENV"] = "dev"
    os.environ["DATABASE_URL"] = f"sqlite+pysqlite:///{(directorio / 'test.sqlite3').as_posix()}"
    os.environ["MP_TICKET"] = ""          # fuerza el proveedor de fixtures
    os.environ["LLM_PROVIDER"] = "null"
    os.environ["STORAGE_LOCAL_RAIZ"] = str(directorio / "files")
    os.environ["NOTIFY_BACKENDS"] = "consola"

    from backend.nucleo.config import obtener_config

    obtener_config.cache_clear()
    yield directorio


@pytest.fixture
def bd(_entorno_de_test):
    """Base de datos limpia por test."""
    from backend.app import _importar_modelos
    from backend.nucleo.auditoria import activar_auditoria_automatica
    from backend.nucleo.db import obtener_motor, reiniciar_conexiones
    from backend.nucleo.modelo_base import Base

    _importar_modelos()
    activar_auditoria_automatica()
    motor = obtener_motor()
    Base.metadata.drop_all(motor)
    Base.metadata.create_all(motor)

    # El almacenamiento de archivos tambien se limpia: si no, el versionado por
    # hash arrastra versiones del test anterior y los conteos dejan de cuadrar.
    from backend.conectores.archivos import reiniciar_storage
    from backend.conectores.archivos.local import StorageLocal

    StorageLocal().borrar_todo()
    reiniciar_storage()

    from backend.nucleo.eventos import BUS
    from backend.nucleo.pendientes import limpiar as limpiar_pendientes

    BUS.limpiar()
    limpiar_pendientes()

    yield
    Base.metadata.drop_all(motor)
    reiniciar_conexiones()


@pytest.fixture
def listado_real() -> list[dict]:
    """Listado real del 04-09-2026: 1.214 licitaciones, capturado de la API."""
    datos = json.loads((FIXTURES / "licitaciones_fecha_04092026.json").read_text("utf-8"))
    return datos["Listado"]


@pytest.fixture
def detalle_real() -> dict:
    """Detalle real de 425-57-LR26 (servicio de inspeccion tecnica)."""
    datos = json.loads((FIXTURES / "licitacion_425-57-LR26.json").read_text("utf-8"))
    return datos["Listado"][0]


@pytest.fixture
def perfil_ito():
    """Perfil equivalente al que se carga como semilla."""
    from backend.modulos.m1_radar.filtro import PerfilEvaluable

    return PerfilEvaluable(
        nombre="ITO",
        palabras_clave=(
            "inspeccion tecnica",
            "ITO",
            "asesoria a la inspeccion",
            "supervision de obras",
        ),
        palabras_excluidas=("suministro", "arriendo", "provision de"),
        categorias_unspsc=("7213",),
        umbral_interes=0.5,
    )
