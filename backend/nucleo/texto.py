"""Normalizacion de texto, compartida por el nucleo y los conectores.

Vive aqui y no en un modulo porque la necesitan capas que no pueden importarse
entre si: el filtro del radar (modulos/) y la busqueda de organismos
(conectores/). Duplicarla habria sido la otra opcion, y duplicar la
normalizacion es como terminan los sistemas donde "SERVIU" y "Serviu" son
cosas distintas.
"""

from __future__ import annotations

import re
import unicodedata


def normalizar(texto: str) -> str:
    """Minusculas sin tildes.

    Las bases y los nombres de organismo mezclan 'INSPECCION', 'Inspección' e
    'inspeccion' sin ningun criterio.
    """
    if not texto:
        return ""
    descompuesto = unicodedata.normalize("NFD", texto.lower())
    return "".join(c for c in descompuesto if unicodedata.category(c) != "Mn")


def patron_de_frase(frase: str) -> re.Pattern[str]:
    """Compila una frase a un patron con limites de palabra.

    Los espacios toleran cualquier separador, porque en las bases aparece
    'inspeccion tecnica', 'inspeccion  tecnica' y 'inspeccion-tecnica'.

    El limite de palabra no es un detalle: buscar la subcadena 'ito ' en el
    listado real marca 'Suministro señaleticas de Transito' como candidata,
    porque 'transito ' contiene 'ito '.
    """
    partes = [re.escape(p) for p in normalizar(frase).split() if p]
    if not partes:
        return re.compile(r"(?!)")  # patron que nunca calza
    return re.compile(r"\b" + r"[\s\-_/]+".join(partes) + r"\b")
