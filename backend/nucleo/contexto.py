"""Contexto de la operación en curso: quién la ejecuta.

Se usa para autoría y auditoría sin tener que pasar el usuario por diez capas.
Un job sin usuario deja `actor=None`, que se registra como "sistema".
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Actor:
    """Quien ejecuta la operación."""

    identificador: str          # email o 'job:m1_radar.sincronizar'
    nombre: str = ""
    rol: str = ""
    es_sistema: bool = False

    @property
    def etiqueta(self) -> str:
        return self.nombre or self.identificador


ACTOR_SISTEMA = Actor(identificador="sistema", nombre="Sistema", es_sistema=True)

_actor_actual: ContextVar[Actor | None] = ContextVar("actor_actual", default=None)


def actor_actual() -> Actor | None:
    return _actor_actual.get()


def actor_o_sistema() -> Actor:
    return _actor_actual.get() or ACTOR_SISTEMA


@contextmanager
def como(actor: Actor) -> Iterator[Actor]:
    """Ejecuta un bloque en nombre de `actor`."""
    token = _actor_actual.set(actor)
    try:
        yield actor
    finally:
        _actor_actual.reset(token)


def como_job(nombre_job: str) -> Actor:
    """Actor para tareas programadas: identifica qué job hizo el cambio."""
    return Actor(identificador=f"job:{nombre_job}", nombre=nombre_job, es_sistema=True)
