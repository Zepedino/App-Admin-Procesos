"""Acceso a base de datos.

Un solo motor por proceso. SQLite en desarrollo, Postgres (Supabase) en producción:
la capa SQLAlchemy es la misma, y el único SQL específico de motor permitido está aquí.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from backend.nucleo.config import Config, obtener_config
from backend.nucleo.logging import obtener_logger

log = obtener_logger(__name__)

_motor: Engine | None = None
_FabricaSesion: sessionmaker[Session] | None = None


def _crear_motor(config: Config) -> Engine:
    url = config.database_url
    kwargs: dict = {"pool_pre_ping": True, "future": True}

    if url.startswith("sqlite"):
        # La ruta del fichero es relativa a la raíz del proyecto; asegurar que exista.
        if ":///" in url and ":memory:" not in url:
            relativa = url.split(":///", 1)[1]
            destino = Path(relativa)
            if not destino.is_absolute():
                destino = config.raiz / destino
                url = f"sqlite+pysqlite:///{destino.as_posix()}"
            destino.parent.mkdir(parents=True, exist_ok=True)
        # timeout: cuanto espera por un lock antes de rendirse.
        #
        # Es imprescindible aqui y no un ajuste fino: el caso normal es tener la
        # aplicacion abierta (con su planificador escribiendo el contador de
        # cuota) y a la vez ejecutar un comando de consola. Sin esto, SQLite
        # aborta de inmediato con "database is locked" y la sincronizacion se
        # cae a media carga, habiendo gastado ya las llamadas a la API.
        kwargs["connect_args"] = {"check_same_thread": False, "timeout": 30.0}

    motor = create_engine(url, **kwargs)

    if url.startswith("sqlite"):
        @event.listens_for(motor, "connect")
        def _pragmas(dbapi_conn, _rec):  # pragma: no cover - configuración de driver
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")   # las FK NO son opcionales
            cur.execute("PRAGMA journal_mode=WAL")  # lectura concurrente con los jobs
            # Espera activa por el lock dentro de SQLite, en milisegundos.
            # Complementa al timeout del driver y cubre los bloqueos que
            # aparecen a mitad de una transaccion, no solo al conectar.
            cur.execute("PRAGMA busy_timeout=30000")
            cur.close()

    log.info("motor de base de datos creado", extra={"dialecto": motor.dialect.name})
    return motor


def obtener_motor() -> Engine:
    global _motor
    if _motor is None:
        _motor = _crear_motor(obtener_config())
    return _motor


def obtener_fabrica_sesion() -> sessionmaker[Session]:
    global _FabricaSesion
    if _FabricaSesion is None:
        _FabricaSesion = sessionmaker(
            bind=obtener_motor(), autoflush=False, expire_on_commit=False, future=True
        )
    return _FabricaSesion


@contextmanager
def sesion() -> Iterator[Session]:
    """Sesión transaccional. Commit al salir bien, rollback ante cualquier excepción."""
    s = obtener_fabrica_sesion()()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()


def dependencia_sesion() -> Iterator[Session]:
    """Dependencia de FastAPI. Usar con `Depends(dependencia_sesion)`."""
    with sesion() as s:
        yield s


def reiniciar_conexiones() -> None:
    """Descarta motor y fábrica. Solo para tests y para `cli doctor`."""
    global _motor, _FabricaSesion
    if _motor is not None:
        _motor.dispose()
    _motor = None
    _FabricaSesion = None
