"""Contrato del proveedor de datos de compras públicas.

Los DTO de este módulo están modelados sobre respuestas REALES de
api.mercadopublico.cl (ver pruebas/fixtures/api/), no sobre la documentación.
Cada campo normalizado indica de qué campo crudo viene.

Todo DTO conserva `crudo`: el JSON original completo. El PRD lo exige en el
modelo de datos (json_crudo) y es lo que permite reprocesar sin volver a gastar
cuota cuando descubramos que necesitábamos un campo que hoy ignoramos.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import IntEnum, StrEnum
from typing import Any

from backend.nucleo.tiempo import parsear_fecha_hora_api


class EstadoLicitacion(IntEnum):
    """Códigos de estado de la API (PRD seccion 4.1)."""

    PUBLICADA = 5
    CERRADA = 6
    DESIERTA = 7
    ADJUDICADA = 8
    REVOCADA = 18
    SUSPENDIDA = 19

    @classmethod
    def desde_codigo(cls, codigo: int | None) -> EstadoLicitacion | None:
        try:
            return cls(int(codigo))  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return None

    @property
    def etiqueta(self) -> str:
        return {
            5: "Publicada",
            6: "Cerrada",
            7: "Desierta",
            8: "Adjudicada",
            18: "Revocada",
            19: "Suspendida",
        }[int(self)]

    @property
    def es_activa(self) -> bool:
        """Activa = todavía se puede ofertar. Determina el TTL de caché."""
        return self is EstadoLicitacion.PUBLICADA


class TipoLicitacion(StrEnum):
    """Tipos relevantes (PRD seccion 4.1).

    El sufijo del código externo los identifica: 425-57-LR26 es de tipo LR.
    """

    L1 = "L1"   # menor a 100 UTM
    LE = "LE"   # entre 100 y 1000 UTM
    LP = "LP"   # mayor a 1000 UTM
    LQ = "LQ"
    LR = "LR"
    LS = "LS"   # servicios personales especializados: probablemente el principal
    LB = "LB"
    LC = "LC"
    LD = "LD"
    LM = "LM"
    LN = "LN"
    LT = "LT"
    LV = "LV"
    CO = "CO"
    OTRO = "OTRO"

    @classmethod
    def desde_texto(cls, texto: str | None) -> TipoLicitacion:
        if not texto:
            return cls.OTRO
        try:
            return cls(texto.strip().upper())
        except ValueError:
            return cls.OTRO


class NaturalezaMonto(IntEnum):
    """Campo Estimacion (PRD seccion 4.1).

    Distingue "hay este presupuesto" de "esto cuesta más o menos esto", que no
    es lo mismo a la hora de ofertar.
    """

    PRESUPUESTO_DISPONIBLE = 1
    PRECIO_REFERENCIAL = 2

    @property
    def etiqueta(self) -> str:
        return {1: "Presupuesto disponible", 2: "Precio referencial"}[int(self)]


def _texto(valor: Any) -> str:
    return str(valor).strip() if valor is not None else ""


def _entero(valor: Any) -> int | None:
    try:
        return int(str(valor).strip())
    except (TypeError, ValueError):
        return None


def _decimal(valor: Any) -> float | None:
    try:
        return float(str(valor).replace(",", "."))
    except (TypeError, ValueError):
        return None


def _bandera(valor: Any) -> bool:
    """La API entrega banderas como texto 0 o 1, no como booleanos."""
    return _texto(valor) in {"1", "true", "True"}


@dataclass(slots=True)
class LicitacionResumen:
    """Lo que devuelve la consulta por fecha.

    Verificado contra la API real: la consulta por fecha SOLO entrega estos
    cuatro campos. El detalle exige una llamada por código, y esa llamada
    cuesta cuota. Esa asimetría es la razón de ser del filtrado previo de M1.
    """

    codigo: str
    nombre: str
    codigo_estado: int | None
    fecha_cierre: datetime | None
    crudo: dict[str, Any] = field(default_factory=dict)

    @property
    def estado(self) -> EstadoLicitacion | None:
        return EstadoLicitacion.desde_codigo(self.codigo_estado)

    @property
    def tipo(self) -> TipoLicitacion:
        partes = self.codigo.split("-")
        if len(partes) < 3:
            return TipoLicitacion.OTRO
        letras = "".join(c for c in partes[-1] if c.isalpha())
        return TipoLicitacion.desde_texto(letras)

    @classmethod
    def desde_api(cls, datos: dict[str, Any]) -> LicitacionResumen:
        return cls(
            codigo=_texto(datos.get("CodigoExterno")),
            nombre=_texto(datos.get("Nombre")),
            codigo_estado=_entero(datos.get("CodigoEstado")),
            fecha_cierre=parsear_fecha_hora_api(datos.get("FechaCierre")),
            crudo=datos,
        )


@dataclass(slots=True)
class Comprador:
    """Bloque Comprador del detalle. Es el organismo licitante."""

    codigo_organismo: str = ""
    nombre_organismo: str = ""
    rut_unidad: str = ""
    codigo_unidad: str = ""
    nombre_unidad: str = ""
    direccion_unidad: str = ""
    comuna_unidad: str = ""
    region_unidad: str = ""
    nombre_usuario: str = ""
    cargo_usuario: str = ""

    @classmethod
    def desde_api(cls, datos: dict[str, Any] | None) -> Comprador:
        d = datos or {}
        return cls(
            codigo_organismo=_texto(d.get("CodigoOrganismo")),
            nombre_organismo=_texto(d.get("NombreOrganismo")),
            rut_unidad=_texto(d.get("RutUnidad")),
            codigo_unidad=_texto(d.get("CodigoUnidad")),
            nombre_unidad=_texto(d.get("NombreUnidad")),
            direccion_unidad=_texto(d.get("DireccionUnidad")),
            comuna_unidad=_texto(d.get("ComunaUnidad")),
            region_unidad=_texto(d.get("RegionUnidad")),
            nombre_usuario=_texto(d.get("NombreUsuario")),
            cargo_usuario=_texto(d.get("CargoUsuario")),
        )


@dataclass(slots=True)
class FechasLicitacion:
    """Bloque Fechas. Alimenta el calendario único (RF-4.3)."""

    creacion: datetime | None = None
    publicacion: datetime | None = None
    inicio_preguntas: datetime | None = None
    fin_preguntas: datetime | None = None
    publicacion_respuestas: datetime | None = None
    cierre: datetime | None = None
    apertura_tecnica: datetime | None = None
    apertura_economica: datetime | None = None
    adjudicacion: datetime | None = None
    estimada_adjudicacion: datetime | None = None
    estimada_firma: datetime | None = None
    visita_terreno: datetime | None = None
    entrega_antecedentes: datetime | None = None
    soporte_fisico: datetime | None = None

    @classmethod
    def desde_api(cls, datos: dict[str, Any] | None) -> FechasLicitacion:
        d = datos or {}
        p = parsear_fecha_hora_api
        return cls(
            creacion=p(d.get("FechaCreacion")),
            publicacion=p(d.get("FechaPublicacion")),
            # OJO: dentro del bloque Fechas, FechaInicio y FechaFinal delimitan
            # el periodo de preguntas del foro, no la vigencia de la licitación.
            inicio_preguntas=p(d.get("FechaInicio")),
            fin_preguntas=p(d.get("FechaFinal")),
            publicacion_respuestas=p(d.get("FechaPubRespuestas")),
            cierre=p(d.get("FechaCierre")),
            apertura_tecnica=p(d.get("FechaActoAperturaTecnica")),
            apertura_economica=p(d.get("FechaActoAperturaEconomica")),
            adjudicacion=p(d.get("FechaAdjudicacion")),
            estimada_adjudicacion=p(d.get("FechaEstimadaAdjudicacion")),
            estimada_firma=p(d.get("FechaEstimadaFirma")),
            visita_terreno=p(d.get("FechaVisitaTerreno")),
            entrega_antecedentes=p(d.get("FechaEntregaAntecedentes")),
            soporte_fisico=p(d.get("FechaSoporteFisico")),
        )


@dataclass(slots=True)
class ItemLicitacion:
    """Producto o servicio licitado.

    La categoría UNSPSC de estos ítems es uno de los filtros del radar (RF-1.2).
    """

    correlativo: int | None = None
    codigo_producto: int | None = None
    codigo_categoria: str = ""
    categoria: str = ""
    nombre_producto: str = ""
    descripcion: str = ""
    unidad_medida: str = ""
    cantidad: float | None = None

    @classmethod
    def desde_api(cls, d: dict[str, Any]) -> ItemLicitacion:
        return cls(
            correlativo=_entero(d.get("Correlativo")),
            codigo_producto=_entero(d.get("CodigoProducto")),
            codigo_categoria=_texto(d.get("CodigoCategoria")),
            categoria=_texto(d.get("Categoria")),
            nombre_producto=_texto(d.get("NombreProducto")),
            descripcion=_texto(d.get("Descripcion")),
            unidad_medida=_texto(d.get("UnidadMedida")),
            cantidad=_decimal(d.get("Cantidad")),
        )


@dataclass(slots=True)
class LicitacionDetalle:
    """Detalle completo (consulta por código).

    Contiene los campos que el PRD seccion 4.1 marca como clave para el scoring.
    """

    codigo: str
    nombre: str
    descripcion: str = ""
    codigo_estado: int | None = None
    estado_texto: str = ""
    tipo: TipoLicitacion = TipoLicitacion.OTRO
    moneda: str = "CLP"

    comprador: Comprador = field(default_factory=Comprador)
    fechas: FechasLicitacion = field(default_factory=FechasLicitacion)
    items: list[ItemLicitacion] = field(default_factory=list)

    # Monto y su naturaleza (PRD seccion 4.1)
    monto_estimado: float | None = None
    naturaleza_monto: NaturalezaMonto | None = None
    visibilidad_monto: int | None = None
    fuente_financiamiento: str = ""

    # Banderas que pesan en el go/no-go
    obras: bool = False
    toma_razon: bool = False
    subcontratacion: bool = False
    extension_plazo: bool = False
    es_renovable: bool = False
    tiene_contrato: bool = False

    # Condiciones contractuales
    modalidad: int | None = None
    tipo_pago: str = ""
    duracion_contrato: str = ""
    unidad_duracion_contrato: int | None = None
    prohibicion_contratacion: str = ""

    dias_cierre: int | None = None
    cantidad_reclamos: int | None = None
    adjudicacion: dict[str, Any] | None = None

    crudo: dict[str, Any] = field(default_factory=dict)

    @property
    def estado(self) -> EstadoLicitacion | None:
        return EstadoLicitacion.desde_codigo(self.codigo_estado)

    @property
    def texto_busqueda(self) -> str:
        """Todo el texto libre junto, para el filtrado por palabras clave de M1."""
        partes = [self.nombre, self.descripcion]
        partes += [i.nombre_producto for i in self.items]
        partes += [i.descripcion for i in self.items]
        partes += [i.categoria for i in self.items]
        return " ".join(p for p in partes if p)

    @property
    def categorias_unspsc(self) -> set[str]:
        return {i.codigo_categoria for i in self.items if i.codigo_categoria}

    @classmethod
    def desde_api(cls, d: dict[str, Any]) -> LicitacionDetalle:
        items_crudos = (d.get("Items") or {}).get("Listado") or []
        estimacion = _entero(d.get("Estimacion"))
        naturaleza = NaturalezaMonto(estimacion) if estimacion in (1, 2) else None
        return cls(
            codigo=_texto(d.get("CodigoExterno")),
            nombre=_texto(d.get("Nombre")),
            descripcion=_texto(d.get("Descripcion")),
            codigo_estado=_entero(d.get("CodigoEstado")),
            estado_texto=_texto(d.get("Estado")),
            tipo=TipoLicitacion.desde_texto(d.get("Tipo")),
            moneda=_texto(d.get("Moneda")) or "CLP",
            comprador=Comprador.desde_api(d.get("Comprador")),
            fechas=FechasLicitacion.desde_api(d.get("Fechas")),
            items=[ItemLicitacion.desde_api(i) for i in items_crudos],
            monto_estimado=_decimal(d.get("MontoEstimado")),
            naturaleza_monto=naturaleza,
            visibilidad_monto=_entero(d.get("VisibilidadMonto")),
            fuente_financiamiento=_texto(d.get("FuenteFinanciamiento")),
            obras=_bandera(d.get("Obras")),
            toma_razon=_bandera(d.get("TomaRazon")),
            subcontratacion=_bandera(d.get("SubContratacion")),
            extension_plazo=_bandera(d.get("ExtensionPlazo")),
            es_renovable=_bandera(d.get("EsRenovable")),
            tiene_contrato=_bandera(d.get("Contrato")),
            modalidad=_entero(d.get("Modalidad")),
            tipo_pago=_texto(d.get("TipoPago")),
            duracion_contrato=_texto(d.get("TiempoDuracionContrato")),
            unidad_duracion_contrato=_entero(d.get("UnidadTiempoDuracionContrato")),
            prohibicion_contratacion=_texto(d.get("ProhibicionContratacion")),
            dias_cierre=_entero(d.get("DiasCierreLicitacion")),
            cantidad_reclamos=_entero(d.get("CantidadReclamos")),
            adjudicacion=d.get("Adjudicacion"),
            crudo=d,
        )


@dataclass(slots=True)
class EstadoCuota:
    """Foto del consumo de cuota del día (PRD seccion 4.2)."""

    fecha: date
    usadas: int
    tope: int
    umbral: int
    usadas_scraper: int = 0

    @property
    def restantes(self) -> int:
        return max(0, self.tope - self.usadas)

    @property
    def porcentaje(self) -> float:
        return (self.usadas / self.tope * 100) if self.tope else 0.0

    @property
    def degradado(self) -> bool:
        """Superado el umbral, el sistema solo refresca lo que cierra en menos de 48h."""
        return self.usadas >= self.umbral

    @property
    def agotada(self) -> bool:
        return self.usadas >= self.tope


class ProcurementProvider(ABC):
    """Contrato único de acceso a datos de compras públicas.

    Toda llamada al exterior pasa por aquí, con caché, reintentos con backoff y
    contador de cuota (PRD seccion 4.2, RNF crítico). Cuando ChileCompra publique
    el portal API unificado se escribe otra implementación de esta clase y el
    resto del sistema no se entera.
    """

    #: Identificador para logs y para el panel de administración.
    nombre: str = "abstracto"

    #: Si es False, los datos no vienen de la API en vivo. La UI lo advierte.
    en_vivo: bool = False

    @abstractmethod
    def licitaciones_del_dia(self, dia: date) -> list[LicitacionResumen]:
        """Licitaciones con movimiento en una fecha. Datos básicos, una sola llamada."""

    @abstractmethod
    def detalle(self, codigo: str, *, forzar_refresco: bool = False) -> LicitacionDetalle | None:
        """Detalle completo por código. Devuelve None si no existe."""

    @abstractmethod
    def licitaciones_por_estado(self, estado: EstadoLicitacion) -> list[LicitacionResumen]:
        """Licitaciones en un estado dado."""

    @abstractmethod
    def licitaciones_por_organismo(self, codigo_organismo: str) -> list[LicitacionResumen]:
        """Histórico de un organismo. Base de la inteligencia competitiva (RF-3.5)."""

    @abstractmethod
    def buscar_organismos(self, texto: str = "") -> list[dict[str, str]]:
        """Catalogo de organismos compradores, filtrable por nombre.

        Necesario para la vigilancia dirigida: hay que poder encontrar el
        codigo de un organismo sin conocerlo de memoria.
        """

    @abstractmethod
    def ordenes_de_compra_por_proveedor(self, rut_proveedor: str) -> list[dict[str, Any]]:
        """Órdenes de compra de la empresa. Cruce automático de RF-6.2."""

    @abstractmethod
    def estado_cuota(self) -> EstadoCuota:
        """Consumo de cuota de hoy. Lo muestra el panel de administración."""
