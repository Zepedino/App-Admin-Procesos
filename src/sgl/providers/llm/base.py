"""Contrato del proveedor de IA y guardas de las reglas duras del PRD seccion 4.4.

Las cinco reglas duras no son documentación: están implementadas aquí.

1. Solo documentos públicos van al LLM  -> `verificar_documento_publico()`, que
   corta la operación en vez de advertir.
2. La IA resume y pre-clasifica, no decide -> el contrato solo devuelve
   `ResultadoIA`, que es información con procedencia, nunca una acción.
3. Todo output va marcado y con fuente -> `CampoExtraido` exige documento y
   página de origen; sin eso no se puede construir.
4. Capa abstracta para cambiar de proveedor -> esta clase.
5. Correcciones humanas registradas -> `CampoExtraido.corregido_por`.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any

from sgl.core.errors import DatoSensibleBloqueado
from sgl.core.logging import obtener_logger
from sgl.core.modelo_base import ahora_utc

log = obtener_logger(__name__)


class OrigenDocumento(StrEnum):
    """De dónde salió el documento. Determina si puede ir al LLM."""

    PORTAL_PUBLICO = "portal_publico"    # bases, anexos, resoluciones publicadas
    RESOLUCION_PUBLICADA = "resolucion_publicada"
    INTERNO = "interno"                  # PROHIBIDO enviarlo
    DATOS_PERSONALES = "datos_personales"  # PROHIBIDO enviarlo

    @property
    def puede_ir_al_llm(self) -> bool:
        return self in {OrigenDocumento.PORTAL_PUBLICO, OrigenDocumento.RESOLUCION_PUBLICADA}


#: Patrones que delatan datos personales chilenos en un texto supuestamente público.
#: No es un detector perfecto y no pretende serlo: es una red de seguridad ante
#: el error de clasificación humana, que es el que va a ocurrir.
PATRONES_SENSIBLES: list[tuple[str, re.Pattern[str]]] = [
    ("rut_persona", re.compile(r"\b\d{1,2}\.\d{3}\.\d{3}-[\dkK]\b")),
    ("remuneracion", re.compile(r"(?i)\b(sueldo|remuneraci[oó]n|liquidaci[oó]n de sueldo|haberes)\b")),
    ("cuenta_bancaria", re.compile(r"(?i)\bcuenta\s+(corriente|vista|rut)\s*(n[°º]|numero|número)?\s*\d{6,}")),
    ("correo_personal", re.compile(r"(?i)\b[\w.+-]+@(gmail|hotmail|outlook|yahoo)\.[a-z.]{2,}\b")),
]


def detectar_datos_sensibles(texto: str) -> list[str]:
    """Devuelve las etiquetas de patrones sensibles encontrados."""
    return [etiqueta for etiqueta, patron in PATRONES_SENSIBLES if patron.search(texto)]


def verificar_documento_publico(texto: str, origen: OrigenDocumento, *, referencia: str = "") -> None:
    """Guarda de la regla dura n.1. Lanza DatoSensibleBloqueado si no procede.

    Se llama SIEMPRE antes de mandar cualquier texto a un LLM. No hay ruta
    alternativa: `LLMProvider.analizar()` la invoca por contrato.

    El tier gratuito de Gemini puede usar los datos para entrenar (PRD seccion 4.4).
    Esto no es una precaución teórica.
    """
    if not origen.puede_ir_al_llm:
        raise DatoSensibleBloqueado(
            "el documento no es público; no puede enviarse a un servicio de IA",
            origen=str(origen),
            referencia=referencia,
        )

    hallazgos = detectar_datos_sensibles(texto)
    if hallazgos:
        log.error(
            "bloqueado envío a LLM por datos sensibles detectados",
            extra={"hallazgos": hallazgos, "referencia": referencia},
        )
        raise DatoSensibleBloqueado(
            "se detectaron datos personales en un documento marcado como público",
            hallazgos=hallazgos,
            referencia=referencia,
        )


@dataclass(slots=True)
class FuenteDato:
    """Procedencia de un dato extraído.

    Regla dura n.3: ningún monto ni fecha generado por el modelo se muestra sin
    el dato original al lado. Para cumplirlo hay que saber dónde estaba.
    """

    documento: str              # nombre del anexo o de las bases
    pagina: int | None = None
    fragmento: str = ""         # el texto literal donde aparece el dato

    def __str__(self) -> str:  # pragma: no cover
        pag = f", p. {self.pagina}" if self.pagina else ""
        return f"{self.documento}{pag}"


@dataclass(slots=True)
class CampoExtraido:
    """Un dato extraído por IA, con su fuente y su historial de corrección.

    Construirlo sin fuente es imposible por diseño: es la garantía estructural
    de la regla dura n.3.
    """

    nombre: str
    valor: Any
    fuente: FuenteDato
    confianza: float | None = None
    valor_corregido: Any = None
    corregido_por: str | None = None
    corregido_en: datetime | None = None

    @property
    def es_de_ia(self) -> bool:
        """Falso una vez que un humano lo corrigió: deja de ser output de IA."""
        return self.corregido_por is None

    @property
    def valor_vigente(self) -> Any:
        return self.valor_corregido if self.corregido_por else self.valor

    def corregir(self, nuevo_valor: Any, *, por: str) -> None:
        """Registra una corrección humana (regla dura n.5).

        Con el tiempo, estas correcciones miden la precisión real del modelo.
        """
        self.valor_corregido = nuevo_valor
        self.corregido_por = por
        self.corregido_en = ahora_utc()


@dataclass(slots=True)
class ResultadoIA:
    """Salida de un análisis. Información con procedencia, nunca una decisión."""

    campos: list[CampoExtraido] = field(default_factory=list)
    texto_libre: str = ""
    modelo: str = ""
    prompt_version: str = ""
    generado_en: datetime = field(default_factory=ahora_utc)
    tokens_entrada: int | None = None
    tokens_salida: int | None = None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None

    def campo(self, nombre: str) -> CampoExtraido | None:
        return next((c for c in self.campos if c.nombre == nombre), None)


@dataclass(slots=True)
class SolicitudAnalisis:
    """Lo que se le pide al modelo."""

    tarea: str                   # 'resumen_bases' | 'tabla_multas' | 'obligaciones'
    texto: str
    origen: OrigenDocumento
    referencia: str = ""         # código de licitación / nombre del anexo
    contexto: dict[str, Any] = field(default_factory=dict)


class LLMProvider(ABC):
    """Contrato de acceso a modelos de lenguaje.

    Cambiar de Gemini a otro proveedor, o del tier gratuito al pagado, es
    escribir otra subclase. La lógica de negocio no se entera (regla dura n.4).
    """

    nombre: str = "abstracto"
    disponible: bool = False

    def analizar(self, solicitud: SolicitudAnalisis) -> ResultadoIA:
        """Punto de entrada único. Aplica la guarda antes de llamar al modelo.

        Es un método concreto y `_analizar` el abstracto, precisamente para que
        una implementación nueva no pueda saltarse la verificación por descuido.
        """
        verificar_documento_publico(
            solicitud.texto, solicitud.origen, referencia=solicitud.referencia
        )
        return self._analizar(solicitud)

    @abstractmethod
    def _analizar(self, solicitud: SolicitudAnalisis) -> ResultadoIA:
        """Implementación concreta. Nunca se llama directamente desde el negocio."""

    @abstractmethod
    def estado(self) -> dict[str, Any]:
        """Diagnóstico para el panel de administración: modelo, cuota, RPM."""
