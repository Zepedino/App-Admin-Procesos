"""Exportacion e importacion de datos de demostracion.

PARA QUE: que alguien clone el repositorio, ejecute el lanzador y vea la
aplicacion con contenido real, sin ticket propio y sin esperar a que
sincronice. Es lo que hace falta para mostrar el avance en una presentacion,
o para que alguien del equipo lo pruebe el primer dia.

QUE SE EXPORTA: licitaciones y organismos tal como los devolvio la API, mas el
perfil de interes vigente. Son **datos publicos de compras del Estado**: no hay
nada sensible, ni el ticket, ni informacion de personas.

QUE NO SE EXPORTA: el estado de seguimiento interno (quien descarto que y por
que), la cuota consumida, la auditoria ni la cache. Son de cada instalacion y
mezclarlos confundiria el historial real con el de una demo.

DATOS PERSONALES: la API incluye el nombre, cargo y correo del funcionario a
cargo de cada licitacion. Son publicos (estan en la ficha del portal), pero no
aportan nada a una demostracion y este archivo SI se versiona. El PRD seccion 6
manda minimizar datos de personas, asi que se anonimizan al exportar. Sin esto,
el repositorio acumularia 66 nombres de funcionarios sin ninguna razon.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sqlalchemy import select

from backend.modulos.m1_radar.models import Licitacion, Organismo, PerfilInteres
from backend.nucleo.db import sesion
from backend.nucleo.logging import obtener_logger
from backend.nucleo.modelo_base import ahora_utc

log = obtener_logger(__name__)

#: Carpeta versionada con los datos de demostracion.
CARPETA_DEMO = "datos_demo"
ARCHIVO_DEMO = "licitaciones_demo.json"


#: Campos del JSON crudo que identifican a una persona. Se vacian al exportar.
CAMPOS_PERSONALES = (
    "NombreUsuario",
    "CargoUsuario",
    "RutUsuario",
    "NombreResponsablePago",
    "EmailResponsablePago",
    "NombreResponsableContrato",
    "EmailResponsableContrato",
    "FonoResponsableContrato",
)


def anonimizar(crudo: dict[str, Any]) -> dict[str, Any]:
    """Devuelve una copia sin los datos del funcionario a cargo.

    No toca el RUT de la unidad compradora: ese identifica al organismo
    (60.x, 61.x son instituciones del Estado), no a una persona.
    """
    copia = dict(crudo)
    for campo in CAMPOS_PERSONALES:
        if campo in copia:
            copia[campo] = ""
    comprador = copia.get("Comprador")
    if isinstance(comprador, dict):
        comprador = dict(comprador)
        for campo in CAMPOS_PERSONALES:
            if campo in comprador:
                comprador[campo] = ""
        copia["Comprador"] = comprador
    return copia


def ruta_demo(raiz: Path | None = None) -> Path:
    from backend.nucleo.config import obtener_config

    base = raiz or obtener_config().raiz
    return base / CARPETA_DEMO / ARCHIVO_DEMO


# --- Exportacion -------------------------------------------------------------


def exportar(destino: Path | None = None, *, limite: int | None = None) -> dict:
    """Vuelca licitaciones, organismos y perfil a un JSON versionable."""
    archivo = destino or ruta_demo()
    archivo.parent.mkdir(parents=True, exist_ok=True)

    with sesion() as s:
        organismos = s.execute(select(Organismo).order_by(Organismo.codigo_mp)).scalars().all()
        consulta = select(Licitacion).order_by(Licitacion.fecha_cierre.desc().nullslast())
        if limite:
            consulta = consulta.limit(limite)
        licitaciones = s.execute(consulta).scalars().all()
        perfiles = s.execute(select(PerfilInteres)).scalars().all()

        datos: dict[str, Any] = {
            "generado_en": ahora_utc().isoformat(),
            "nota": (
                "Datos reales de Mercado Publico capturados para demostracion. "
                "Informacion publica de compras del Estado. No contiene secretos."
            ),
            "organismos": [
                {
                    "codigo_mp": o.codigo_mp,
                    "nombre": o.nombre,
                    "rut": o.rut,
                    "region": o.region,
                    "comuna": o.comuna,
                    "lista_negra": o.lista_negra,
                    "motivo_lista_negra": o.motivo_lista_negra,
                    "lista_blanca": o.lista_blanca,
                    "vigilado": o.vigilado,
                }
                for o in organismos
            ],
            "perfiles": [
                {
                    "nombre": p.nombre,
                    "activo": p.activo,
                    "descripcion": p.descripcion,
                    "palabras_clave": p.palabras_clave,
                    "palabras_excluidas": p.palabras_excluidas,
                    "categorias_unspsc": p.categorias_unspsc,
                    "regiones": p.regiones,
                    "tipos_licitacion": p.tipos_licitacion,
                    "monto_minimo": p.monto_minimo,
                    "monto_maximo": p.monto_maximo,
                    "solo_obras": p.solo_obras,
                    "umbral_interes": p.umbral_interes,
                }
                for p in perfiles
            ],
            # El JSON crudo basta para reconstruirlo todo: es la respuesta
            # literal de la API, el mismo camino que usa la sincronizacion real.
            "licitaciones": [
                {
                    "codigo": lic.codigo,
                    "organismo_codigo_mp": (
                        lic.organismo.codigo_mp if lic.organismo else None
                    ),
                    "puntaje_perfil": lic.puntaje_perfil,
                    "coincidencias": lic.coincidencias,
                    "json_crudo": anonimizar(lic.json_crudo),
                }
                for lic in licitaciones
                if lic.json_crudo
            ],
        }

    archivo.write_text(
        json.dumps(datos, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    resumen = {
        "archivo": str(archivo),
        "licitaciones": len(datos["licitaciones"]),
        "organismos": len(datos["organismos"]),
        "perfiles": len(datos["perfiles"]),
        "kb": round(archivo.stat().st_size / 1024),
    }
    log.info("datos de demostracion exportados", extra=resumen)
    return resumen


# --- Importacion -------------------------------------------------------------


def importar(origen: Path | None = None, *, solo_si_vacio: bool = True) -> dict:
    """Carga los datos de demostracion. Por defecto, solo si no hay nada.

    `solo_si_vacio` evita el accidente de sobreescribir el trabajo real de una
    instalacion en uso con datos de demo al reiniciar la aplicacion.
    """
    from backend.conectores.mercado_publico.base import LicitacionDetalle
    from backend.modulos.m1_radar.services import guardar_detalle

    archivo = origen or ruta_demo()
    resumen = {"licitaciones": 0, "organismos": 0, "perfiles": 0, "omitido": False}

    if not archivo.exists():
        log.info("no hay datos de demostracion que cargar", extra={"archivo": str(archivo)})
        resumen["omitido"] = True
        return resumen

    with sesion() as s:
        if solo_si_vacio and s.execute(select(Licitacion).limit(1)).first():
            resumen["omitido"] = True
            return resumen

    datos = json.loads(archivo.read_text(encoding="utf-8"))

    # Organismos primero: las licitaciones los referencian, y traen las marcas
    # de vigilancia y lista negra, que son decisiones de negocio.
    with sesion() as s:
        existentes = set(s.execute(select(Organismo.codigo_mp)).scalars().all())
        for o in datos.get("organismos", []):
            if o["codigo_mp"] in existentes:
                continue
            s.add(Organismo(**o))
            resumen["organismos"] += 1

        if not s.execute(select(PerfilInteres).limit(1)).first():
            for p in datos.get("perfiles", []):
                s.add(PerfilInteres(**p))
                resumen["perfiles"] += 1

    # Las licitaciones entran por el mismo camino que la sincronizacion real,
    # no por INSERT directo: asi la demo ejercita el codigo de verdad y no
    # puede quedar en un estado que la sincronizacion nunca produciria.
    for entrada in datos.get("licitaciones", []):
        crudo = entrada.get("json_crudo")
        if not crudo:
            continue
        try:
            with sesion() as s:
                guardar_detalle(s, LicitacionDetalle.desde_api(crudo))
                resumen["licitaciones"] += 1
        except Exception:
            log.exception("no se pudo cargar una licitacion de demo",
                          extra={"codigo": entrada.get("codigo")})

    log.info("datos de demostracion cargados", extra=resumen)
    return resumen
