"""Vigilancia dirigida de organismos (RF-1.2, lista blanca).

EL PROBLEMA QUE RESUELVE, encontrado con datos reales:

El listado diario de la API entrega solo cuatro campos por licitacion y
**ninguno es el organismo comprador**. Eso obliga a filtrar por palabras del
nombre, con una consecuencia que no se ve hasta que se mide: si el cliente
principal titula sus licitaciones de una forma que el perfil no contempla, se
pierden todas y nadie se entera, porque no hay nada que mirar.

Paso exactamente eso. En 8.132 licitaciones de 7 dias habiles el radar capturo
cero licitaciones del SERVIU. No porque no hubiera: el SERVIU las llama
"Fiscalizacion Tecnica de Obras" (FTO), y el perfil buscaba "inspeccion
tecnica". Habia 11 del rubro exacto, incluidas varias de los programas DS49 y
DS27, y todas pasaron de largo.

LA SOLUCION:

Para los organismos marcados como vigilados se consulta su codigo directamente
(`CodigoOrganismo=X&estado=activas`), lo que devuelve TODAS sus licitaciones
abiertas sin depender de como las hayan titulado. Trece SERVIU son trece
llamadas de las 10.000 diarias: 0,13 % de la cuota por eliminar el punto ciego.

Las palabras clave siguen sirviendo para descubrir organismos nuevos; la
vigilancia dirigida garantiza los que ya sabemos que importan. Son
complementarias, no alternativas.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select

from backend.conectores.mercado_publico import obtener_proveedor
from backend.conectores.mercado_publico.cuota import CUOTA
from backend.modulos.m1_radar.models import Licitacion, Organismo
from backend.nucleo.auditoria import registrar
from backend.nucleo.db import sesion
from backend.nucleo.errors import CuotaAgotada
from backend.nucleo.logging import obtener_logger
from backend.nucleo.modelo_base import ahora_utc

log = obtener_logger(__name__)

#: Texto con el que se buscan los SERVIU en el catalogo de organismos.
#:
#: Verificado contra la API: de los 899 organismos compradores, solo UNO se
#: llama "SERVIU" (el de Magallanes). Los otros doce figuran como "SERVICIO DE
#: VIVIENDA Y URBANIZACION <region>". Buscar la sigla encuentra uno de trece,
#: que es justo el tipo de error silencioso que este modulo existe para evitar.
BUSQUEDAS_SERVIU = ("servicio de vivienda y urbanizacion", "serviu")


@dataclass
class ResultadoVigilancia:
    """Lo que encontro una pasada de vigilancia."""

    organismos_consultados: int = 0
    licitaciones_vistas: int = 0
    nuevas: int = 0
    actualizadas: int = 0
    detalles_pedidos: int = 0
    errores: list[str] = field(default_factory=list)

    def a_dict(self) -> dict:
        return {
            "organismos_consultados": self.organismos_consultados,
            "licitaciones_vistas": self.licitaciones_vistas,
            "nuevas": self.nuevas,
            "actualizadas": self.actualizadas,
            "detalles_pedidos": self.detalles_pedidos,
            "errores": self.errores,
        }


# --- Descubrimiento ----------------------------------------------------------


def descubrir_organismos(texto: str) -> list[dict[str, str]]:
    """Busca organismos por nombre en el catalogo de la API.

    Una sola llamada, cacheada 30 dias: el catalogo casi no cambia.
    """
    return obtener_proveedor().buscar_organismos(texto)


def marcar_vigilados(codigos: list[str], *, nombres: dict[str, str] | None = None) -> int:
    """Marca organismos para vigilancia dirigida. Devuelve cuantos cambiaron.

    Crea el organismo si todavia no existe en la base: se puede vigilar a
    alguien del que aun no hemos visto ninguna licitacion, que es precisamente
    el caso que motiva este modulo.
    """
    nombres = nombres or {}
    cambiados = 0

    with sesion() as s:
        for codigo in codigos:
            organismo = s.execute(
                select(Organismo).where(Organismo.codigo_mp == codigo)
            ).scalar_one_or_none()

            if organismo is None:
                organismo = Organismo(
                    codigo_mp=codigo,
                    nombre=nombres.get(codigo, codigo),
                    vigilado=True,
                    vigilado_desde=ahora_utc(),
                    lista_blanca=True,
                )
                s.add(organismo)
                cambiados += 1
            elif not organismo.vigilado:
                organismo.vigilado = True
                organismo.vigilado_desde = ahora_utc()
                organismo.lista_blanca = True
                cambiados += 1
            else:
                continue

            registrar(
                s,
                accion="marcar_vigilado",
                entidad="Organismo",
                entidad_id=codigo,
                valor_nuevo=True,
                motivo="vigilancia dirigida: garantiza no perder sus licitaciones",
                modulo="m1_radar",
            )

    log.info("organismos marcados para vigilancia", extra={"cambiados": cambiados})
    return cambiados


def organismos_vigilados() -> list[tuple[str, str]]:
    with sesion() as s:
        filas = (
            s.execute(
                select(Organismo.codigo_mp, Organismo.nombre)
                .where(Organismo.vigilado.is_(True))
                .order_by(Organismo.nombre)
            )
            .all()
        )
    return [(c, n) for c, n in filas]


# --- Vigilancia --------------------------------------------------------------


def revisar_organismos_vigilados(*, limite_detalles: int = 40) -> ResultadoVigilancia:
    """Consulta cada organismo vigilado y guarda sus licitaciones activas.

    Una llamada por organismo, mas una por cada licitacion que todavia no
    conocemos. No se aplica el filtro de palabras clave: si decidimos vigilar a
    un organismo es porque TODO lo que publique nos interesa revisar. Filtrarlo
    reintroduciria el punto ciego que este modulo elimina.
    """
    from backend.modulos.m1_radar.services import (
        evaluar_contra_perfiles,
        guardar_detalle,
        perfiles_activos,
    )

    proveedor = obtener_proveedor()
    resultado = ResultadoVigilancia()
    vigilados = organismos_vigilados()

    if not vigilados:
        log.info("no hay organismos vigilados; nada que revisar")
        return resultado

    # Fase de consulta: una llamada por organismo, sin tocar la base.
    por_revisar: list[str] = []
    with sesion() as s:
        conocidos = set(s.execute(select(Licitacion.codigo)).scalars().all())
        perfiles = perfiles_activos(s)

    for codigo_organismo, nombre in vigilados:
        if not CUOTA.hay_disponible(1) and proveedor.en_vivo:
            resultado.errores.append(f"sin cuota para revisar {nombre}")
            break
        try:
            activas = proveedor.licitaciones_por_organismo(codigo_organismo)
            resultado.organismos_consultados += 1
        except CuotaAgotada as exc:
            resultado.errores.append(str(exc))
            break
        except Exception as exc:
            resultado.errores.append(f"{nombre}: {type(exc).__name__}: {exc}")
            log.exception("fallo al consultar organismo", extra={"organismo": codigo_organismo})
            continue

        resultado.licitaciones_vistas += len(activas)
        por_revisar.extend(r.codigo for r in activas if r.codigo not in conocidos)

    # Fase de detalle: transaccion corta por licitacion, nunca envolviendo la red.
    for codigo in por_revisar[:limite_detalles]:
        if not CUOTA.hay_disponible(1) and proveedor.en_vivo:
            break
        try:
            detalle = proveedor.detalle(codigo)
            resultado.detalles_pedidos += 1
        except Exception as exc:
            resultado.errores.append(f"{codigo}: {type(exc).__name__}: {exc}")
            continue
        if detalle is None:
            continue

        # Se evalua contra el perfil pero NO se descarta nada: de un organismo
        # vigilado queremos verlo todo. El puntaje sirve para ordenar la
        # bandeja, que es distinto de filtrar.
        #
        # Importa de verdad: el SERVIU publica licitaciones llamadas "LP
        # 110-2026", sin una sola palabra util en el nombre. Filtrarlas por
        # palabras clave las perderia; puntuarlas las deja abajo en la lista,
        # que es lo correcto cuando no se sabe lo que son.
        veredicto = evaluar_contra_perfiles(perfiles, detalle)[0] if perfiles else None

        try:
            with sesion() as s:
                _, es_nueva, _ = guardar_detalle(s, detalle, veredicto=veredicto)
                resultado.nuevas += int(es_nueva)
                resultado.actualizadas += int(not es_nueva)
        except Exception as exc:
            resultado.errores.append(f"{codigo}: al guardar: {type(exc).__name__}: {exc}")
            log.exception("no se pudo guardar", extra={"codigo": codigo})

    log.info("vigilancia de organismos terminada", extra=resultado.a_dict())
    return resultado
