"""Aplicacion de migraciones de esquema (Alembic).

POR QUE EXISTE: `create_all` crea tablas que faltan, pero NO agrega columnas a
tablas que ya existen. Al agregar el campo `vigilado` a Organismo, la base de
desarrollo siguio sin la columna y todo lo que la usaba fallaba con
"no such column". En produccion, con datos reales dentro, eso no se arregla
borrando la base.

Envuelto aqui para que el arranque y la consola compartan exactamente el mismo
camino, y para que nadie tenga que saber usar Alembic desde la terminal.
"""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config as ConfigAlembic
from sqlalchemy import inspect

from backend.nucleo.config import obtener_config
from backend.nucleo.db import obtener_motor
from backend.nucleo.logging import obtener_logger

log = obtener_logger(__name__)


def _config_alembic() -> ConfigAlembic:
    raiz = obtener_config().raiz
    cfg = ConfigAlembic(str(raiz / "alembic.ini"))
    cfg.set_main_option("script_location", str(raiz / "migraciones"))
    cfg.set_main_option("sqlalchemy.url", obtener_config().database_url)
    return cfg


def aplicar_migraciones() -> None:
    """Lleva el esquema a la ultima version. Idempotente.

    Se ejecuta al arrancar: si la base ya esta al dia no hace nada, y si falta
    algo lo aplica antes de que la aplicacion atienda la primera peticion.
    """
    cfg = _config_alembic()
    motor = obtener_motor()

    with motor.begin() as conexion:
        # Reusar la conexion del motor en vez de abrir otra: con SQLite, dos
        # conexiones escribiendo el esquema a la vez se bloquean.
        cfg.attributes["connection"] = conexion
        command.upgrade(cfg, "head")

    log.info("esquema de base de datos al dia")


def version_actual() -> str | None:
    from alembic.runtime.migration import MigrationContext

    with obtener_motor().connect() as conexion:
        return MigrationContext.configure(conexion).get_current_revision()


def tablas_existentes() -> list[str]:
    return sorted(inspect(obtener_motor()).get_table_names())


def hay_migraciones_pendientes() -> bool:
    """Para el diagnostico: avisa si el codigo espera un esquema mas nuevo."""
    from alembic.script import ScriptDirectory

    guiones = ScriptDirectory.from_config(_config_alembic())
    return version_actual() != guiones.get_current_head()


def ruta_migraciones() -> Path:
    return obtener_config().raiz / "migraciones" / "versions"
