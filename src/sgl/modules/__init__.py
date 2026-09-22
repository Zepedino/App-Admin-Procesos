"""Módulos del sistema.

Esta lista es el mapa completo del PRD. Cada entrada declara su estado REAL,
no el deseado: /sistema/modulos y docs/ESTADO.md se generan desde aquí, así que
mentir en este archivo se nota de inmediato.

Agregar un módulo:
  1. Crear el paquete `mN_nombre/` con la anatomía descrita en CLAUDE.md.
  2. Exponer un `MODULO: Modulo` en su `__init__.py`.
  3. Añadirlo a `_MANIFIESTOS` aquí abajo.
No hay paso 4. Si tuviste que tocar `core/`, el diseño falló.

Regla de dependencia: un módulo NO importa otro módulo. Se comunican por el bus
de eventos (`core/eventos.py`).
"""

from __future__ import annotations

import functools

from sgl.core.registro import EstadoModulo, Modulo, RegistroDeModulos


def _manifiestos() -> list[Modulo]:
    """Importa los manifiestos. Import diferido para evitar ciclos al arrancar."""
    from sgl.modules.m0_procesos import MODULO as m0
    from sgl.modules.m1_radar import MODULO as m1

    construidos = [m0, m1]

    # Módulos aún no construidos. Se declaran para que el sistema muestre el
    # mapa completo y no se pueda confundir "no existe" con "no lo encuentro".
    planificados = [
        Modulo(
            id="m2_fichas",
            nombre="Ficha consolidada y descarga de anexos",
            descripcion=(
                "Scraper de la ficha pública, versionado por hash, checklist documental "
                "y biblioteca de documentos de la empresa con vencimientos."
            ),
            fase=1,
            estado=EstadoModulo.PLANIFICADO,
            requisitos=tuple(f"RF-2.{i}" for i in range(1, 10)),
            depende_de=("m1_radar",),
            notas=(
                "Antes de activarlo hay que revisar los términos de uso del portal "
                "y fijar SCRAPER_CONTACTO_EMAIL (RF-2.3)."
            ),
        ),
        Modulo(
            id="m3_analisis",
            nombre="Análisis IA y scoring go/no-go",
            descripcion=(
                "Resumen de bases, tabla de multas, obligaciones contractuales, "
                "scoring ponderado e inteligencia competitiva por organismo."
            ),
            fase=2,
            estado=EstadoModulo.PLANIFICADO,
            requisitos=tuple(f"RF-3.{i}" for i in range(1, 7)),
            depende_de=("m2_fichas",),
            notas=(
                "Bloqueado por la pregunta abierta 5 del PRD: sin los criterios reales "
                "de Daniela no se puede programar el scoring."
            ),
        ),
        Modulo(
            id="m4_pipeline",
            nombre="Pipeline, calendario y capacidad",
            descripcion="Kanban del ciclo de vida, calendario único exportable y simulador de capacidad.",
            fase=1,
            estado=EstadoModulo.PLANIFICADO,
            requisitos=tuple(f"RF-4.{i}" for i in range(1, 6)),
            depende_de=("m1_radar",),
        ),
        Modulo(
            id="m5_adjudicacion",
            nombre="Adjudicación y puesta en marcha",
            descripcion=(
                "Plan de puesta en marcha con fechas calculadas desde la adjudicación, "
                "checklist preventivo de multas y ficha de contrato viva."
            ),
            fase=3,
            estado=EstadoModulo.PLANIFICADO,
            requisitos=tuple(f"RF-5.{i}" for i in range(1, 7)),
            depende_de=("m3_analisis",),
            notas="Insumo directo: pregunta abierta 8 (qué hacen hoy en los primeros 10 días).",
        ),
        Modulo(
            id="m6_pagos",
            nombre="Estados de pago, garantías y flujo de caja",
            descripcion="Ciclo de cobro, proyección de caja a 90+ días, cobranza y control de garantías.",
            fase=3,
            estado=EstadoModulo.PLANIFICADO,
            requisitos=tuple(f"RF-6.{i}" for i in range(1, 7)),
            depende_de=("m5_adjudicacion",),
        ),
        Modulo(
            id="m7_multas",
            nombre="Multas",
            descripcion="Registro, plazo de descargos con alerta crítica, patrones y biblioteca de descargos.",
            fase=3,
            estado=EstadoModulo.PLANIFICADO,
            requisitos=tuple(f"RF-7.{i}" for i in range(1, 7)),
            depende_de=("m5_adjudicacion",),
        ),
        Modulo(
            id="m8_terreno",
            nombre="Terreno, visitas y horas",
            descripcion="Programación con agrupación geográfica, registro offline, informes y rentabilidad real.",
            fase=4,
            estado=EstadoModulo.PLANIFICADO,
            requisitos=tuple(f"RF-8.{i}" for i in range(1, 6)),
            depende_de=("m5_adjudicacion",),
            notas=(
                "RESTRICCIÓN LEGAL: v1 es control de gestión de horas, NO registro legal "
                "de asistencia. Requiere autorización de la Dirección del Trabajo. "
                "Verificar Ley 21.719 antes de construir."
            ),
        ),
        Modulo(
            id="m9_reportes",
            nombre="Reportes y Excel",
            descripcion="Importación de planillas actuales, exportación a los formatos del SERVIU y dashboard gerencial.",
            fase=3,
            estado=EstadoModulo.PLANIFICADO,
            requisitos=tuple(f"RF-9.{i}" for i in range(1, 5)),
        ),
        Modulo(
            id="m10_notificaciones",
            nombre="Notificaciones",
            descripcion="Canales por urgencia, preferencias por usuario e ingesta del correo de Mercado Público.",
            fase=1,
            estado=EstadoModulo.PLANIFICADO,
            requisitos=tuple(f"RF-10.{i}" for i in range(1, 5)),
            notas="La capa de proveedores ya existe (providers/notify). Falta el módulo de negocio.",
        ),
        Modulo(
            id="m11_documental",
            nombre="Repositorio documental y firma",
            descripcion="Repositorio versionado, trazabilidad del circuito de firma electrónica avanzada y plantillas.",
            fase=3,
            estado=EstadoModulo.PLANIFICADO,
            requisitos=tuple(f"RF-11.{i}" for i in range(1, 4)),
            notas="NO se firma dentro de la app: está regulado y ya tienen la herramienta (RF-11.2).",
        ),
    ]

    return construidos + planificados


@functools.lru_cache(maxsize=1)
def obtener_registro() -> RegistroDeModulos:
    registro = RegistroDeModulos()
    for modulo in _manifiestos():
        registro.registrar(modulo)
    return registro


def reiniciar_registro() -> None:
    obtener_registro.cache_clear()
