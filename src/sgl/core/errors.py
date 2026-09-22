"""Errores del dominio.

Todos heredan de `SGLError` para que la capa web pueda distinguir un fallo esperado
(que se muestra al usuario) de un bug (que se registra y alerta).

PRD §6: "Un job que falla reintenta y avisa; jamás falla en silencio."
"""

from __future__ import annotations


class SGLError(Exception):
    """Raíz de todos los errores propios. Nunca se lanza directamente."""

    codigo = "sgl_error"
    mensaje_usuario = "Ocurrió un error en el sistema."

    def __init__(self, detalle: str = "", **contexto: object) -> None:
        self.detalle = detalle
        self.contexto = contexto
        super().__init__(detalle or self.mensaje_usuario)

    def __str__(self) -> str:  # pragma: no cover - trivial
        base = self.detalle or self.mensaje_usuario
        if self.contexto:
            extra = " ".join(f"{k}={v!r}" for k, v in self.contexto.items())
            return f"{base} [{extra}]"
        return base


# ─── Configuración ───────────────────────────────────────────────────────────


class ErrorDeConfiguracion(SGLError):
    codigo = "config_invalida"
    mensaje_usuario = "La configuración del sistema es inválida o está incompleta."


# ─── Proveedores externos ────────────────────────────────────────────────────


class ErrorDeProveedor(SGLError):
    """Fallo al hablar con un sistema externo (API, LLM, correo, storage)."""

    codigo = "proveedor_falla"
    mensaje_usuario = "Un servicio externo no respondió correctamente."


class ProveedorNoDisponible(ErrorDeProveedor):
    """El externo está caído o dio 5xx. Reintentable.

    La API de Mercado Público está etiquetada como beta: esto se espera (PRD §4.2).
    """

    codigo = "proveedor_no_disponible"
    mensaje_usuario = "El servicio externo no está disponible en este momento."


class RespuestaInesperada(ErrorDeProveedor):
    """El externo respondió, pero con una forma que no reconocemos.

    Señal típica de que la API o el HTML del portal cambió (riesgo §9 del PRD).
    Es un error VISIBLE a propósito: no se traga.
    """

    codigo = "respuesta_inesperada"
    mensaje_usuario = "El servicio externo respondió en un formato no reconocido."


class CuotaAgotada(ErrorDeProveedor):
    """Se alcanzó el tope diario de llamadas. NO reintentable hoy.

    PRD §4.2: 10.000 solicitudes/día por ticket, tope no modificable.
    """

    codigo = "cuota_agotada"
    mensaje_usuario = "Se agotó la cuota diaria de llamadas a la API. Se retoma mañana."


class FueraDeVentanaBatch(ErrorDeProveedor):
    """Se intentó una carga masiva fuera de 22:00-07:00 (PRD §4.2)."""

    codigo = "fuera_de_ventana"
    mensaje_usuario = "Las cargas masivas solo se ejecutan entre 22:00 y 07:00."


# ─── Reglas de negocio ───────────────────────────────────────────────────────


class ReglaDeNegocioViolada(SGLError):
    codigo = "regla_violada"
    mensaje_usuario = "La operación no cumple una regla del sistema."


class NoEncontrado(SGLError):
    codigo = "no_encontrado"
    mensaje_usuario = "No se encontró lo solicitado."


class PermisoDenegado(SGLError):
    codigo = "permiso_denegado"
    mensaje_usuario = "No tienes permiso para esta operación."


class DatoSensibleBloqueado(SGLError):
    """Se intentó enviar datos de personas a un servicio externo.

    Regla dura de IA n.º 1 (PRD §4.4): solo documentos públicos van al LLM.
    Esto no es una advertencia: corta la operación.
    """

    codigo = "dato_sensible_bloqueado"
    mensaje_usuario = "Bloqueado: se intentó enviar datos sensibles a un servicio externo."
