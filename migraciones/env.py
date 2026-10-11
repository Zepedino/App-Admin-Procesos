"""Entorno de Alembic.

La URL de la base NO se escribe en alembic.ini: se toma de la configuracion
del sistema, que la lee de DATABASE_URL. Asi hay una sola fuente de verdad y
la cadena de conexion de produccion (Supabase) nunca llega al repositorio.
"""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from backend.app import _importar_modelos
from backend.nucleo.config import obtener_config
from backend.nucleo.modelo_base import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Importar todos los modelos antes de leer los metadatos: sin esto, Alembic no
# ve las tablas de un modulo cuyas rutas no se hayan tocado y genera una
# migracion que borra medio esquema.
_importar_modelos()
target_metadata = Base.metadata

config.set_main_option("sqlalchemy.url", obtener_config().database_url)


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    conexion_externa = config.attributes.get("connection", None)

    if conexion_externa is not None:
        _ejecutar(conexion_externa)
        return

    motor = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with motor.connect() as conexion:
        _ejecutar(conexion)


def _ejecutar(conexion) -> None:
    context.configure(
        connection=conexion,
        target_metadata=target_metadata,
        compare_type=True,
        # SQLite no soporta ALTER COLUMN: el batch mode recrea la tabla.
        # Sin esto, cualquier cambio de columna falla solo en desarrollo.
        render_as_batch=conexion.dialect.name == "sqlite",
    )
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
