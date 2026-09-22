"""Bus de eventos interno.

Es el mecanismo por el que un módulo reacciona a otro SIN importarlo. Ejemplos
del PRD: M1 detecta un cambio de bases → M2 re-scrapea; M7 registra una multa →
M3 baja el score del organismo; M5 crea una tarea → M10 notifica.

Cada acoplamiento vía bus es un acoplamiento que se puede quitar sin tocar código
ajeno, que es exactamente lo que pide "modular y reparable".

Síncrono a propósito: con 3-10 usuarios y este volumen, una cola sería
infraestructura sin beneficio. La interfaz permite cambiarlo después.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sgl.core.logging import obtener_logger
from sgl.core.modelo_base import ahora_utc

log = obtener_logger(__name__)


@dataclass(frozen=True, slots=True)
class Evento:
    """Algo que ocurrió. Nombre en pasado, siempre."""

    nombre: str
    datos: dict[str, Any] = field(default_factory=dict)
    ocurrido_en: datetime = field(default_factory=ahora_utc)
    origen: str = ""

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.nombre}({', '.join(f'{k}={v!r}' for k, v in self.datos.items())})"


Manejador = Callable[[Evento], None]


class BusDeEventos:
    """Registro de suscriptores. Un fallo en un manejador no tumba a los demás."""

    def __init__(self) -> None:
        self._suscriptores: dict[str, list[tuple[str, Manejador]]] = defaultdict(list)
        self._historial: list[Evento] = []
        self._max_historial = 500

    def suscribir(self, nombre_evento: str, manejador: Manejador, *, etiqueta: str = "") -> None:
        etiqueta = etiqueta or getattr(manejador, "__qualname__", repr(manejador))
        self._suscriptores[nombre_evento].append((etiqueta, manejador))
        log.debug("suscripción registrada", extra={"evento": nombre_evento, "manejador": etiqueta})

    def publicar(self, evento: Evento) -> list[str]:
        """Entrega el evento a sus suscriptores. Devuelve las etiquetas que fallaron.

        Un manejador que revienta se registra como ERROR y **no** interrumpe la
        publicación ni la transacción del emisor. Fallar visiblemente, no ruidosamente.
        """
        self._historial.append(evento)
        del self._historial[: max(0, len(self._historial) - self._max_historial)]

        fallidos: list[str] = []
        for etiqueta, manejador in self._suscriptores.get(evento.nombre, []):
            try:
                manejador(evento)
            except Exception:
                fallidos.append(etiqueta)
                log.exception(
                    "manejador de evento falló",
                    extra={"evento": evento.nombre, "manejador": etiqueta},
                )
        return fallidos

    def emitir(self, nombre_evento: str, /, *, origen: str = "", **datos: Any) -> list[str]:
        """Atajo: `bus.emitir("licitacion.detectada", codigo="1509-5-L126")`.

        El nombre del evento es posicional-solo a proposito: los datos del evento
        usan libremente claves como `nombre` o `codigo`, y sin esto colisionarian
        con la firma del metodo.
        """
        return self.publicar(Evento(nombre=nombre_evento, datos=datos, origen=origen))

    def suscriptores_de(self, nombre_evento: str) -> list[str]:
        return [e for e, _ in self._suscriptores.get(nombre_evento, [])]

    def eventos_registrados(self) -> list[str]:
        return sorted(self._suscriptores)

    def historial(self, limite: int = 50) -> list[Evento]:
        return self._historial[-limite:]

    def limpiar(self) -> None:
        """Solo para tests."""
        self._suscriptores.clear()
        self._historial.clear()


BUS = BusDeEventos()


class Eventos:
    """Catálogo de nombres de evento.

    Estar aquí es el contrato: si un nombre no está en esta lista, no existe.
    Evita que dos módulos se suscriban a cadenas con errores de tipeo.
    """

    # M1 — Radar
    LICITACION_DETECTADA = "licitacion.detectada"
    LICITACION_CAMBIO = "licitacion.cambio_detectado"        # RF-1.4 adendas
    LICITACION_MARCADA_INTERESA = "licitacion.marcada_interesa"
    LICITACION_DESCARTADA = "licitacion.descartada"
    LICITACION_CIERRA_PRONTO = "licitacion.cierra_pronto"

    # M2 — Ficha y anexos
    ANEXO_DESCARGADO = "anexo.descargado"
    ANEXO_NUEVA_VERSION = "anexo.nueva_version"              # RF-2.4 hash cambió
    SCRAPING_FALLIDO = "scraping.fallido"                    # RF-2.3 fallar visiblemente
    DOCUMENTO_EMPRESA_POR_VENCER = "documento_empresa.por_vencer"

    # M3 — IA y scoring
    ANALISIS_IA_COMPLETADO = "analisis_ia.completado"
    SCORING_CALCULADO = "scoring.calculado"
    DECISION_TOMADA = "decision.tomada"

    # M4 — Pipeline
    ITEM_ESTANCADO = "pipeline.item_estancado"               # RF-4.5 escalamiento
    CAPACIDAD_EXCEDIDA = "capacidad.excedida"                # RF-4.4

    # M5 — Adjudicación y puesta en marcha
    LICITACION_ADJUDICADA = "licitacion.adjudicada"
    CONTRATO_CREADO = "contrato.creado"
    PLAN_PUESTA_EN_MARCHA_GENERADO = "puesta_en_marcha.plan_generado"
    TAREA_VENCIDA = "tarea.vencida"
    CONTRATO_CERRADO = "contrato.cerrado"

    # M6 — Pagos y caja
    ESTADO_PAGO_ATRASADO = "estado_pago.atrasado"
    GARANTIA_POR_VENCER = "garantia.por_vencer"
    DEFICIT_CAJA_PROYECTADO = "caja.deficit_proyectado"      # RF-6.3

    # M7 — Multas
    MULTA_REGISTRADA = "multa.registrada"
    PLAZO_DESCARGOS_POR_VENCER = "multa.plazo_descargos_por_vencer"  # RF-7.2 máxima prioridad

    # M8 — Terreno
    VISITA_SINCRONIZADA = "visita.sincronizada"

    # Transversales
    CUOTA_API_EN_UMBRAL = "cuota_api.en_umbral"             # PRD §4.2 degradación al 80%
    JOB_FALLIDO = "job.fallido"                             # PRD §6 nunca en silencio
    PROCEDIMIENTO_SIN_REVISAR = "procedimiento.sin_revisar"  # RF-0.3
