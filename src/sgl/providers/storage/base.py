"""Contrato de almacenamiento de archivos.

PRD RF-2.4 y RF-11.1: repositorio versionado con hash SHA-256 por archivo.
El hash no es un adorno: es lo que detecta que una adenda modificó las bases
sin que nadie avise (RF-2.4).
"""

from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import BinaryIO


def sha256_de(datos: bytes) -> str:
    return hashlib.sha256(datos).hexdigest()


@dataclass(slots=True)
class ArchivoGuardado:
    """Resultado de guardar un archivo."""

    ruta: str            # ruta logica: licitaciones/1509-5-L126/anexos/bases.pdf
    hash_sha256: str
    tamano_bytes: int
    guardado_en: datetime
    version: int = 1
    es_nueva_version: bool = False   # el contenido cambio respecto de la version previa
    contenido_identico: bool = False  # ya existia con el mismo hash: no se duplico


class StorageProvider(ABC):
    """Almacen de archivos con versionado por hash."""

    nombre: str = "abstracto"

    @abstractmethod
    def guardar(self, ruta: str, datos: bytes | BinaryIO) -> ArchivoGuardado:
        """Guarda un archivo. Si el hash cambio, crea una version nueva (RF-2.4)."""

    @abstractmethod
    def leer(self, ruta: str, version: int | None = None) -> bytes:
        """Lee un archivo. Sin version, la ultima."""

    @abstractmethod
    def existe(self, ruta: str) -> bool: ...

    @abstractmethod
    def versiones(self, ruta: str) -> list[ArchivoGuardado]:
        """Historial de versiones, de la mas antigua a la mas reciente."""

    @abstractmethod
    def listar(self, prefijo: str) -> list[str]:
        """Rutas logicas bajo un prefijo."""

    @abstractmethod
    def ruta_fisica(self, ruta: str, version: int | None = None) -> str:
        """Ruta real en disco o URL. Para servir el archivo al navegador."""
