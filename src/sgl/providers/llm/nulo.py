"""Proveedor de IA inactivo.

Es el proveedor por defecto: sin GEMINI_API_KEY el sistema NO llama a nadie y
lo dice explícitamente en la interfaz, en vez de mostrar campos vacíos que el
usuario podría confundir con "el modelo no encontró nada".
"""

from __future__ import annotations

from typing import Any

from sgl.providers.llm.base import LLMProvider, ResultadoIA, SolicitudAnalisis


class ProveedorNulo(LLMProvider):
    nombre = "nulo"
    disponible = False

    def _analizar(self, solicitud: SolicitudAnalisis) -> ResultadoIA:
        return ResultadoIA(
            modelo="ninguno",
            error=(
                "No hay proveedor de IA configurado. "
                "El análisis automático está desactivado; los campos se llenan a mano."
            ),
        )

    def estado(self) -> dict[str, Any]:
        return {
            "proveedor": self.nombre,
            "disponible": False,
            "motivo": "LLM_PROVIDER=null o falta GEMINI_API_KEY",
        }
