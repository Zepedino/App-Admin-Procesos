"""Acceso a modelos de lenguaje. Punto único: `obtener_llm()`."""

from __future__ import annotations

import functools

from backend.conectores.ia.base import (
    CampoExtraido,
    FuenteDato,
    LLMProvider,
    OrigenDocumento,
    ResultadoIA,
    SolicitudAnalisis,
    verificar_documento_publico,
)
from backend.nucleo.config import obtener_config
from backend.nucleo.logging import obtener_logger

log = obtener_logger(__name__)

__all__ = [
    "CampoExtraido",
    "FuenteDato",
    "LLMProvider",
    "OrigenDocumento",
    "ResultadoIA",
    "SolicitudAnalisis",
    "obtener_llm",
    "reiniciar_llm",
    "verificar_documento_publico",
]


@functools.lru_cache(maxsize=1)
def obtener_llm() -> LLMProvider:
    cfg = obtener_config()
    if cfg.llm.provider == "gemini" and cfg.gemini.api_key:
        from backend.conectores.ia.gemini import ProveedorGemini

        log.info("proveedor de IA: Gemini", extra={"modelo": cfg.gemini.modelo})
        return ProveedorGemini()

    from backend.conectores.ia.nulo import ProveedorNulo

    return ProveedorNulo()


def reiniciar_llm() -> None:
    obtener_llm.cache_clear()
