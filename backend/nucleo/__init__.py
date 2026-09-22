"""Núcleo del sistema.

Regla de dependencia (testeada en pruebas/test_arquitectura.py):
`core` NO importa `modules` ni `providers`. El núcleo no sabe qué módulos existen;
son los módulos los que se registran contra él.
"""
