"""Filtro del perfil de interes (RF-1.2).

Logica pura: entra un resumen o un detalle de la API y un perfil, sale un
veredicto explicado. Sin base de datos, sin red. Es la pieza mas facil de
testear y la que mas se va a ajustar, asi que esta aislada a proposito.

POR QUE ESTO NO ES UN SIMPLE "SI CONTIENE LA PALABRA":

Al probar contra el listado real del 04-09-2026 (1.214 licitaciones), buscar la
subcadena "ito " marco como candidata a "Suministro señaleticas de Transito 2026",
porque "transito " contiene "ito ". Un radar que entrega esa basura se deja de
mirar en una semana. De ahi que el emparejamiento sea por limite de palabra y
que el resultado incluya SIEMPRE que palabra hizo match, para poder auditarlo.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any

#: Peso de cada senal en el puntaje final. Editable sin tocar la logica.
PESOS = {
    "palabra_clave": 0.55,
    "categoria_unspsc": 0.20,
    "region": 0.15,
    "tipo": 0.10,
}


def normalizar(texto: str) -> str:
    """Minusculas sin tildes. Las bases mezclan 'INSPECCION' e 'Inspeccion'."""
    if not texto:
        return ""
    descompuesto = unicodedata.normalize("NFD", texto.lower())
    return "".join(c for c in descompuesto if unicodedata.category(c) != "Mn")


def _patron_de(frase: str) -> re.Pattern[str]:
    """Compila una frase a un patron con limites de palabra.

    Los espacios de la frase toleran cualquier separador, porque en las bases
    aparece 'inspeccion tecnica', 'inspeccion  tecnica' y 'inspeccion-tecnica'.
    """
    partes = [re.escape(p) for p in normalizar(frase).split() if p]
    if not partes:
        return re.compile(r"(?!)")  # patron que nunca calza
    return re.compile(r"\b" + r"[\s\-_/]+".join(partes) + r"\b")


@dataclass(slots=True)
class Veredicto:
    """Resultado del filtro, con la explicacion de por que.

    Nunca devolvemos solo un numero: si el encargado no puede ver por que una
    licitacion aparecio en su bandeja, no confia en el radar.
    """

    candidata: bool
    puntaje: float
    palabras_encontradas: list[str] = field(default_factory=list)
    palabras_excluidas_encontradas: list[str] = field(default_factory=list)
    categorias_coincidentes: list[str] = field(default_factory=list)
    region_coincide: bool | None = None
    tipo_coincide: bool | None = None
    motivo_rechazo: str = ""
    perfil: str = ""

    @property
    def explicacion(self) -> str:
        if not self.candidata:
            return self.motivo_rechazo or "no cumple el perfil"
        partes = []
        if self.palabras_encontradas:
            partes.append("palabras: " + ", ".join(self.palabras_encontradas))
        if self.categorias_coincidentes:
            partes.append("categorias: " + ", ".join(self.categorias_coincidentes))
        if self.region_coincide:
            partes.append("region incluida")
        if self.tipo_coincide:
            partes.append("tipo incluido")
        return "; ".join(partes) or "coincide con el perfil"

    def a_dict(self) -> dict[str, Any]:
        """Para guardar en Licitacion.coincidencias y poder auditar despues."""
        return {
            "perfil": self.perfil,
            "puntaje": round(self.puntaje, 3),
            "palabras": self.palabras_encontradas,
            "excluidas": self.palabras_excluidas_encontradas,
            "categorias": self.categorias_coincidentes,
            "region_coincide": self.region_coincide,
            "tipo_coincide": self.tipo_coincide,
            "explicacion": self.explicacion,
        }


@dataclass(slots=True)
class PerfilEvaluable:
    """Version en memoria de PerfilInteres, sin dependencia de la base de datos.

    Permite testear el filtro y, mas adelante, simular cambios de perfil sobre
    el historico antes de guardarlos ("si hubiera tenido este perfil, que habria
    entrado el mes pasado").
    """

    nombre: str = "perfil"
    palabras_clave: tuple[str, ...] = ()
    palabras_excluidas: tuple[str, ...] = ()
    categorias_unspsc: tuple[str, ...] = ()
    regiones: tuple[str, ...] = ()
    comunas: tuple[str, ...] = ()
    tipos_licitacion: tuple[str, ...] = ()
    monto_minimo: float | None = None
    monto_maximo: float | None = None
    solo_obras: bool = False
    umbral_interes: float = 0.5

    @classmethod
    def desde_modelo(cls, perfil: Any) -> PerfilEvaluable:
        return cls(
            nombre=perfil.nombre,
            palabras_clave=tuple(perfil.palabras_clave or ()),
            palabras_excluidas=tuple(perfil.palabras_excluidas or ()),
            categorias_unspsc=tuple(perfil.categorias_unspsc or ()),
            regiones=tuple(perfil.regiones or ()),
            comunas=tuple(perfil.comunas or ()),
            tipos_licitacion=tuple(perfil.tipos_licitacion or ()),
            monto_minimo=perfil.monto_minimo,
            monto_maximo=perfil.monto_maximo,
            solo_obras=bool(perfil.solo_obras),
            umbral_interes=float(perfil.umbral_interes),
        )


def _buscar(frases: tuple[str, ...], texto_normalizado: str) -> list[str]:
    return [f for f in frases if _patron_de(f).search(texto_normalizado)]


def evaluar_texto(perfil: PerfilEvaluable, texto: str) -> Veredicto:
    """Primera pasada, solo con el nombre.

    Es la unica informacion que entrega el listado por fecha de la API, y es
    barata: evita pedir 1.214 detalles para quedarse con 8. Cada detalle cuesta
    una llamada de las 10.000 diarias.
    """
    normalizado = normalizar(texto)
    veredicto = Veredicto(candidata=False, puntaje=0.0, perfil=perfil.nombre)

    excluidas = _buscar(perfil.palabras_excluidas, normalizado)
    if excluidas:
        veredicto.palabras_excluidas_encontradas = excluidas
        veredicto.motivo_rechazo = f"contiene palabra excluida: {', '.join(excluidas)}"
        return veredicto

    encontradas = _buscar(perfil.palabras_clave, normalizado)
    if not encontradas:
        veredicto.motivo_rechazo = "ninguna palabra clave del perfil aparece en el nombre"
        return veredicto

    veredicto.palabras_encontradas = encontradas
    veredicto.candidata = True
    # Con una sola senal disponible, el puntaje no puede superar su peso.
    veredicto.puntaje = PESOS["palabra_clave"]
    return veredicto


def evaluar_detalle(perfil: PerfilEvaluable, detalle: Any) -> Veredicto:
    """Segunda pasada, con el detalle completo.

    `detalle` es un LicitacionDetalle del provider. Se tipa como Any para no
    acoplar el filtro a la forma del proveedor: si manana cambia la API, cambia
    el adaptador, no esta funcion.
    """
    normalizado = normalizar(detalle.texto_busqueda)
    veredicto = Veredicto(candidata=False, puntaje=0.0, perfil=perfil.nombre)

    excluidas = _buscar(perfil.palabras_excluidas, normalizado)
    if excluidas:
        veredicto.palabras_excluidas_encontradas = excluidas
        veredicto.motivo_rechazo = f"contiene palabra excluida: {', '.join(excluidas)}"
        return veredicto

    if perfil.solo_obras and not getattr(detalle, "obras", False):
        veredicto.motivo_rechazo = "el perfil exige licitaciones de obras"
        return veredicto

    monto = getattr(detalle, "monto_estimado", None)
    if monto is not None:
        if perfil.monto_minimo is not None and monto < perfil.monto_minimo:
            veredicto.motivo_rechazo = f"monto {monto:,.0f} bajo el minimo del perfil"
            return veredicto
        if perfil.monto_maximo is not None and monto > perfil.monto_maximo:
            veredicto.motivo_rechazo = f"monto {monto:,.0f} sobre el maximo del perfil"
            return veredicto
    # Si el monto es None no se descarta: VisibilidadMonto=0 es frecuente y no
    # significa que la licitacion no sirva, solo que el organismo no lo publico.

    puntaje = 0.0

    encontradas = _buscar(perfil.palabras_clave, normalizado)
    veredicto.palabras_encontradas = encontradas
    if encontradas:
        puntaje += PESOS["palabra_clave"]

    if perfil.categorias_unspsc:
        categorias = getattr(detalle, "categorias_unspsc", set()) or set()
        coincidentes = sorted(
            c for c in categorias if any(c.startswith(p) for p in perfil.categorias_unspsc)
        )
        veredicto.categorias_coincidentes = coincidentes
        if coincidentes:
            puntaje += PESOS["categoria_unspsc"]

    if perfil.regiones:
        region = normalizar(getattr(detalle.comprador, "region_unidad", "") or "")
        veredicto.region_coincide = any(normalizar(r) in region for r in perfil.regiones)
        if veredicto.region_coincide:
            puntaje += PESOS["region"]

    if perfil.tipos_licitacion:
        tipo = str(getattr(detalle, "tipo", "") or "")
        veredicto.tipo_coincide = tipo in perfil.tipos_licitacion
        if veredicto.tipo_coincide:
            puntaje += PESOS["tipo"]

    veredicto.puntaje = round(puntaje, 3)
    # Sin ninguna palabra clave no es candidata, aunque sume por region o tipo:
    # "es del SERVIU de la region correcta" no basta si no es de nuestro rubro.
    veredicto.candidata = bool(encontradas) and puntaje >= perfil.umbral_interes
    if not veredicto.candidata:
        veredicto.motivo_rechazo = (
            "sin palabras clave" if not encontradas
            else f"puntaje {puntaje:.2f} bajo el umbral {perfil.umbral_interes:.2f}"
        )
    return veredicto


def evaluar_contra_perfiles(
    perfiles: list[PerfilEvaluable], detalle: Any
) -> tuple[Veredicto, list[Veredicto]]:
    """Evalua contra todos los perfiles activos y devuelve el mejor.

    Una licitacion califica si calza con al menos un perfil. Se devuelven todos
    los veredictos para poder mostrar por que los demas la rechazaron.
    """
    if not perfiles:
        return Veredicto(candidata=False, puntaje=0.0, motivo_rechazo="no hay perfiles activos"), []
    todos = [evaluar_detalle(p, detalle) for p in perfiles]
    mejor = max(todos, key=lambda v: (v.candidata, v.puntaje))
    return mejor, todos
