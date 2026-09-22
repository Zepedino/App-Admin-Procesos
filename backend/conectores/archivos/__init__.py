"""Almacenamiento de archivos. Punto único: `obtener_storage()`."""

from __future__ import annotations

import functools

from backend.conectores.archivos.base import ArchivoGuardado, StorageProvider
from backend.nucleo.config import obtener_config

__all__ = ["ArchivoGuardado", "StorageProvider", "obtener_storage", "reiniciar_storage"]


@functools.lru_cache(maxsize=1)
def obtener_storage() -> StorageProvider:
    cfg = obtener_config()
    if cfg.storage.backend == "s3":
        raise NotImplementedError(
            "backend S3 aún no implementado; usar STORAGE_BACKEND=local"
        )
    from backend.conectores.archivos.local import StorageLocal

    return StorageLocal()


def reiniciar_storage() -> None:
    obtener_storage.cache_clear()
