"""Logging estructurado.

Regla del PRD §6: nada falla en silencio. Cada fallo deja registro con contexto
suficiente para reconstruir qué pasó sin tener que reproducirlo.
"""

from __future__ import annotations

import json
import logging
import sys
from typing import Any

CAMPOS_ESTANDAR = {
    "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
    "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
    "created", "msecs", "relativeCreated", "thread", "threadName",
    "processName", "process", "taskName", "message", "asctime",
}


class FormateadorJSON(logging.Formatter):
    """Una línea JSON por evento. Legible por máquina, grepeable por humano."""

    def format(self, record: logging.LogRecord) -> str:
        salida: dict[str, Any] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "nivel": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        for clave, valor in record.__dict__.items():
            if clave not in CAMPOS_ESTANDAR and not clave.startswith("_"):
                salida[clave] = valor
        if record.exc_info:
            salida["excepcion"] = self.formatException(record.exc_info)
        return json.dumps(salida, ensure_ascii=False, default=str)


class FormateadorConsola(logging.Formatter):
    """Formato corto para desarrollo."""

    def format(self, record: logging.LogRecord) -> str:
        extra = {
            k: v
            for k, v in record.__dict__.items()
            if k not in CAMPOS_ESTANDAR and not k.startswith("_")
        }
        cola = ("  " + " ".join(f"{k}={v}" for k, v in extra.items())) if extra else ""
        base = f"{record.levelname:<8} {record.name:<28} {record.getMessage()}{cola}"
        if record.exc_info:
            base += "\n" + self.formatException(record.exc_info)
        return base


def configurar_logging(nivel: str = "INFO", *, json_salida: bool = False) -> None:
    """Configura el logging del proceso. Idempotente."""
    raiz = logging.getLogger()
    for h in list(raiz.handlers):
        raiz.removeHandler(h)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(FormateadorJSON() if json_salida else FormateadorConsola())
    raiz.addHandler(handler)
    raiz.setLevel(nivel.upper())

    # Ruido de terceros que no aporta.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("apscheduler.executors").setLevel(logging.WARNING)


def obtener_logger(nombre: str) -> logging.Logger:
    return logging.getLogger(nombre)
