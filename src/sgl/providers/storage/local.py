"""Almacenamiento en disco local con versionado por hash SHA-256.

Estructura fisica:

    var/files/<ruta-logica>/v001__<hash12>.<ext>
    var/files/<ruta-logica>/manifiesto.json

El manifiesto guarda el historial. Guardar el mismo contenido dos veces no crea
version nueva; guardar contenido distinto SI, y eso es exactamente la deteccion
de adendas que pide RF-2.4.
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import BinaryIO

from sgl.core.config import obtener_config
from sgl.core.errors import NoEncontrado
from sgl.core.logging import obtener_logger
from sgl.core.modelo_base import ahora_utc
from sgl.providers.storage.base import ArchivoGuardado, StorageProvider, sha256_de

log = obtener_logger(__name__)

NOMBRE_MANIFIESTO = "manifiesto.json"


class StorageLocal(StorageProvider):
    nombre = "local"

    def __init__(self, raiz: Path | str | None = None) -> None:
        cfg = obtener_config()
        self._raiz = Path(raiz) if raiz else cfg.ruta(cfg.storage.local_raiz)
        self._raiz.mkdir(parents=True, exist_ok=True)

    # --- Rutas ---------------------------------------------------------------

    def _normalizar(self, ruta: str) -> str:
        limpia = ruta.strip().strip("/").replace("\\", "/")
        if not limpia or ".." in limpia.split("/"):
            raise ValueError(f"ruta logica invalida: {ruta!r}")
        return limpia

    def _carpeta(self, ruta: str) -> Path:
        return self._raiz / self._normalizar(ruta)

    def _manifiesto(self, ruta: str) -> list[dict]:
        archivo = self._carpeta(ruta) / NOMBRE_MANIFIESTO
        if not archivo.exists():
            return []
        try:
            return json.loads(archivo.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            log.error("manifiesto corrupto", extra={"ruta": ruta})
            return []

    def _escribir_manifiesto(self, ruta: str, entradas: list[dict]) -> None:
        carpeta = self._carpeta(ruta)
        carpeta.mkdir(parents=True, exist_ok=True)
        (carpeta / NOMBRE_MANIFIESTO).write_text(
            json.dumps(entradas, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    # --- Contrato ------------------------------------------------------------

    def guardar(self, ruta: str, datos: bytes | BinaryIO) -> ArchivoGuardado:
        contenido = datos if isinstance(datos, bytes) else datos.read()
        digest = sha256_de(contenido)
        entradas = self._manifiesto(ruta)

        if entradas and entradas[-1]["hash_sha256"] == digest:
            ultima = entradas[-1]
            return ArchivoGuardado(
                ruta=ruta,
                hash_sha256=digest,
                tamano_bytes=ultima["tamano_bytes"],
                guardado_en=datetime.fromisoformat(ultima["guardado_en"]),
                version=ultima["version"],
                contenido_identico=True,
            )

        version = (entradas[-1]["version"] + 1) if entradas else 1
        extension = Path(self._normalizar(ruta)).suffix or ".bin"
        nombre_fisico = f"v{version:03d}__{digest[:12]}{extension}"
        carpeta = self._carpeta(ruta)
        carpeta.mkdir(parents=True, exist_ok=True)
        (carpeta / nombre_fisico).write_bytes(contenido)

        momento = ahora_utc()
        entradas.append(
            {
                "version": version,
                "hash_sha256": digest,
                "tamano_bytes": len(contenido),
                "guardado_en": momento.isoformat(),
                "archivo": nombre_fisico,
            }
        )
        self._escribir_manifiesto(ruta, entradas)

        es_nueva = version > 1
        if es_nueva:
            # RF-2.4: el contenido cambio. Casi siempre significa adenda.
            log.warning(
                "archivo cambio de contenido: nueva version",
                extra={"ruta": ruta, "version": version, "hash": digest[:12]},
            )
        return ArchivoGuardado(
            ruta=ruta,
            hash_sha256=digest,
            tamano_bytes=len(contenido),
            guardado_en=momento,
            version=version,
            es_nueva_version=es_nueva,
        )

    def leer(self, ruta: str, version: int | None = None) -> bytes:
        entradas = self._manifiesto(ruta)
        if not entradas:
            raise NoEncontrado(f"no hay archivo en {ruta}", ruta=ruta)
        entrada = (
            entradas[-1]
            if version is None
            else next((e for e in entradas if e["version"] == version), None)
        )
        if entrada is None:
            raise NoEncontrado(f"no existe la version {version} de {ruta}", ruta=ruta)
        return (self._carpeta(ruta) / entrada["archivo"]).read_bytes()

    def existe(self, ruta: str) -> bool:
        return bool(self._manifiesto(ruta))

    def versiones(self, ruta: str) -> list[ArchivoGuardado]:
        return [
            ArchivoGuardado(
                ruta=ruta,
                hash_sha256=e["hash_sha256"],
                tamano_bytes=e["tamano_bytes"],
                guardado_en=datetime.fromisoformat(e["guardado_en"]),
                version=e["version"],
                es_nueva_version=e["version"] > 1,
            )
            for e in self._manifiesto(ruta)
        ]

    def listar(self, prefijo: str) -> list[str]:
        base = self._carpeta(prefijo) if prefijo else self._raiz
        if not base.exists():
            return []
        return sorted(
            str(m.parent.relative_to(self._raiz)).replace("\\", "/")
            for m in base.rglob(NOMBRE_MANIFIESTO)
        )

    def ruta_fisica(self, ruta: str, version: int | None = None) -> str:
        entradas = self._manifiesto(ruta)
        if not entradas:
            raise NoEncontrado(f"no hay archivo en {ruta}", ruta=ruta)
        entrada = (
            entradas[-1]
            if version is None
            else next((e for e in entradas if e["version"] == version), None)
        )
        if entrada is None:
            raise NoEncontrado(f"no existe la version {version} de {ruta}", ruta=ruta)
        return str(self._carpeta(ruta) / entrada["archivo"])

    def espacio_usado_bytes(self) -> int:
        return sum(f.stat().st_size for f in self._raiz.rglob("*") if f.is_file())

    def borrar_todo(self) -> None:
        """Solo para tests."""
        if self._raiz.exists():
            shutil.rmtree(self._raiz)
        self._raiz.mkdir(parents=True, exist_ok=True)
