"""Adaptadores al mundo exterior.

Cada subpaquete define un contrato abstracto (`base.py`) y una o más
implementaciones intercambiables. La lógica de negocio depende del contrato,
nunca de la implementación.

Es lo que permite cumplir el PRD seccion 4.2 sin reescribir el sistema:
"Cuando salga la API nueva se reescribe el adaptador y nada más."

Regla de dependencia: `providers` NO importa `modules`.
"""
