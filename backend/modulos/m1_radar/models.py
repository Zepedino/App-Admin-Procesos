"""Modelos de M1 - Radar de oportunidades.

Sigue el modelo de datos del PRD seccion 7. La Licitacion es LA entidad del
sistema: entra por el radar y sale meses despues como contrato cerrado, sin
volver a digitarse. Por eso vive aqui y no en un modulo posterior.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.nucleo.auditoria import Auditable
from backend.nucleo.modelo_base import Base, FechaHoraUTC, ModeloBase


class OrigenLicitacion(StrEnum):
    """PRD seccion 7: origen radar, manual o codigo pegado.

    Importa para RF-5.1: se puede pegar el codigo de una licitacion que nunca
    paso por el radar y el sistema la trae igual.
    """

    RADAR = "radar"
    MANUAL = "manual"
    CODIGO_PEGADO = "codigo_pegado"
    CORREO = "correo"          # llego por la ingesta de correo de M10


class EstadoSeguimiento(StrEnum):
    """Estado interno nuestro, distinto del estado de la licitacion en el portal.

    El portal dice Publicada; nosotros decimos "ya la descarte". Son dos ejes
    independientes, y confundirlos es el error clasico de estos sistemas.
    """

    NUEVA = "nueva"                # detectada, nadie la ha mirado
    EN_REVISION = "en_revision"
    INTERESA = "interesa"          # dispara el scraper de M2 (RF-2.2)
    DESCARTADA = "descartada"      # con motivo tipificado obligatorio (RF-1.5)
    EN_PREPARACION = "en_preparacion"
    OFERTADA = "ofertada"
    ADJUDICADA = "adjudicada"
    PERDIDA = "perdida"

    @property
    def etiqueta(self) -> str:
        return {
            "nueva": "Nueva",
            "en_revision": "En revision",
            "interesa": "Interesa",
            "descartada": "Descartada",
            "en_preparacion": "En preparacion",
            "ofertada": "Ofertada",
            "adjudicada": "Adjudicada",
            "perdida": "Perdida",
        }[self.value]


class MotivoDescarte(StrEnum):
    """RF-1.5: motivo tipificado obligatorio.

    "En 6 meses estos datos dicen si los criterios sirven." Por eso es un enum
    y no texto libre: sobre texto libre no se puede agregar nada.
    """

    FUERA_DE_RUBRO = "fuera_de_rubro"
    MONTO_INSUFICIENTE = "monto_insuficiente"
    DISTANCIA_EXCESIVA = "distancia_excesiva"
    SIN_CAPACIDAD = "sin_capacidad"
    ORGANISMO_EXCLUIDO = "organismo_excluido"
    PLAZO_INSUFICIENTE = "plazo_insuficiente"
    REQUISITOS_NO_CUMPLIDOS = "requisitos_no_cumplidos"
    EXPOSICION_A_MULTAS = "exposicion_a_multas"
    CONDICIONES_DE_PAGO = "condiciones_de_pago"
    COMPETENCIA_DESFAVORABLE = "competencia_desfavorable"
    OTRO = "otro"

    @property
    def etiqueta(self) -> str:
        return {
            "fuera_de_rubro": "Fuera de nuestro rubro",
            "monto_insuficiente": "Monto insuficiente",
            "distancia_excesiva": "Distancia o costo de traslado excesivo",
            "sin_capacidad": "Sin capacidad en el periodo",
            "organismo_excluido": "Organismo en lista negra",
            "plazo_insuficiente": "Plazo insuficiente para preparar la oferta",
            "requisitos_no_cumplidos": "No cumplimos requisitos de las bases",
            "exposicion_a_multas": "Exposicion a multas demasiado alta",
            "condiciones_de_pago": "Condiciones de pago incompatibles con la caja",
            "competencia_desfavorable": "Competencia desfavorable",
            "otro": "Otro motivo",
        }[self.value]


class Organismo(ModeloBase, Auditable):
    """PRD seccion 7: Organismo.

    La lista negra con motivo registrado es el hallazgo 8 (municipalidades
    excluidas): la decision queda documentada, no en la memoria de alguien.
    """

    __tablename__ = "organismos"
    __modulo_auditoria__ = "m1_radar"
    __auditar_campos__ = {"lista_negra", "motivo_lista_negra", "riesgo_pago"}

    codigo_mp: Mapped[str] = mapped_column(String(40), unique=True, index=True, nullable=False)
    nombre: Mapped[str] = mapped_column(String(300), nullable=False)
    rut: Mapped[str | None] = mapped_column(String(20))
    region: Mapped[str | None] = mapped_column(String(120), index=True)
    comuna: Mapped[str | None] = mapped_column(String(120))

    lista_negra: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    motivo_lista_negra: Mapped[str | None] = mapped_column(Text)
    lista_blanca: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Alimentado por M6 (RF-6.6) y ponderado por el scoring de M3.
    riesgo_pago: Mapped[str | None] = mapped_column(String(20))
    dias_pago_promedio: Mapped[int | None] = mapped_column(Integer)

    licitaciones: Mapped[list[Licitacion]] = relationship(back_populates="organismo")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Organismo {self.codigo_mp} {self.nombre[:40]}>"


class Licitacion(ModeloBase, Auditable):
    """PRD seccion 7: Licitacion. La entidad central del sistema.

    json_crudo guarda la respuesta completa de la API. Ocupa espacio y vale la
    pena: permite reprocesar sin gastar cuota cuando descubramos que hacia falta
    un campo que hoy no mapeamos.
    """

    __tablename__ = "licitaciones"
    __modulo_auditoria__ = "m1_radar"
    __auditar_campos__ = {
        "estado_seguimiento",
        "motivo_descarte",
        "monto_estimado",
        "codigo_estado",
        "fecha_cierre",
        "responsable",
    }
    __table_args__ = (
        Index("ix_licitaciones_seguimiento_cierre", "estado_seguimiento", "fecha_cierre"),
        Index("ix_licitaciones_estado_mp", "codigo_estado"),
    )

    codigo: Mapped[str] = mapped_column(String(40), unique=True, index=True, nullable=False)
    nombre: Mapped[str] = mapped_column(String(500), nullable=False)
    descripcion: Mapped[str | None] = mapped_column(Text)

    organismo_id: Mapped[int | None] = mapped_column(ForeignKey("organismos.id"))
    organismo: Mapped[Organismo | None] = relationship(back_populates="licitaciones")
    nombre_organismo: Mapped[str | None] = mapped_column(String(300))
    region: Mapped[str | None] = mapped_column(String(120), index=True)
    comuna: Mapped[str | None] = mapped_column(String(120))

    tipo: Mapped[str | None] = mapped_column(String(10), index=True)
    codigo_estado: Mapped[int | None] = mapped_column(Integer)
    estado_texto: Mapped[str | None] = mapped_column(String(40))

    monto_estimado: Mapped[float | None] = mapped_column(Float)
    naturaleza_monto: Mapped[int | None] = mapped_column(Integer)
    moneda: Mapped[str | None] = mapped_column(String(10))
    visibilidad_monto: Mapped[int | None] = mapped_column(Integer)

    fecha_publicacion: Mapped[datetime | None] = mapped_column(FechaHoraUTC)
    fecha_cierre: Mapped[datetime | None] = mapped_column(FechaHoraUTC, index=True)
    fecha_fin_preguntas: Mapped[datetime | None] = mapped_column(FechaHoraUTC)
    fecha_pub_respuestas: Mapped[datetime | None] = mapped_column(FechaHoraUTC)
    fecha_apertura_tecnica: Mapped[datetime | None] = mapped_column(FechaHoraUTC)
    fecha_adjudicacion: Mapped[datetime | None] = mapped_column(FechaHoraUTC)
    fecha_visita_terreno: Mapped[datetime | None] = mapped_column(FechaHoraUTC)

    obras: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    toma_razon: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    subcontratacion: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    es_renovable: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    tipo_pago: Mapped[str | None] = mapped_column(String(10))

    # --- Seguimiento interno ---
    origen: Mapped[str] = mapped_column(String(20), default=OrigenLicitacion.RADAR, nullable=False)
    estado_seguimiento: Mapped[str] = mapped_column(
        String(20), default=EstadoSeguimiento.NUEVA, nullable=False, index=True
    )
    motivo_descarte: Mapped[str | None] = mapped_column(String(40))
    detalle_descarte: Mapped[str | None] = mapped_column(Text)
    descartada_por: Mapped[str | None] = mapped_column(String(120))
    descartada_en: Mapped[datetime | None] = mapped_column(FechaHoraUTC)
    responsable: Mapped[str | None] = mapped_column(String(120))

    # Resultado del filtro del perfil de interes (RF-1.2)
    puntaje_perfil: Mapped[float | None] = mapped_column(Float)
    coincidencias: Mapped[dict | None] = mapped_column(JSON)

    detectada_en: Mapped[datetime | None] = mapped_column(FechaHoraUTC)
    detalle_obtenido_en: Mapped[datetime | None] = mapped_column(FechaHoraUTC)
    json_crudo: Mapped[dict | None] = mapped_column(JSON)

    cambios: Mapped[list[CambioDetectado]] = relationship(
        back_populates="licitacion", cascade="all, delete-orphan"
    )

    @property
    def esta_abierta(self) -> bool:
        return self.codigo_estado == 5

    @property
    def fue_descartada(self) -> bool:
        return self.estado_seguimiento == EstadoSeguimiento.DESCARTADA

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Licitacion {self.codigo} {self.estado_seguimiento}>"


class CambioDetectado(ModeloBase):
    """RF-1.4: deteccion de cambios y adendas.

    Si cambia la fecha de cierre, se publica una aclaracion o se modifica el
    monto, queda registrado el diff. Es la diferencia entre enterarse y no
    enterarse de que movieron el cierre.
    """

    __tablename__ = "cambios_detectados"
    __table_args__ = (Index("ix_cambios_licitacion_fecha", "licitacion_id", "detectado_en"),)

    licitacion_id: Mapped[int] = mapped_column(
        ForeignKey("licitaciones.id", ondelete="CASCADE"), nullable=False
    )
    licitacion: Mapped[Licitacion] = relationship(back_populates="cambios")

    campo: Mapped[str] = mapped_column(String(80), nullable=False)
    valor_anterior: Mapped[str | None] = mapped_column(Text)
    valor_nuevo: Mapped[str | None] = mapped_column(Text)
    detectado_en: Mapped[datetime] = mapped_column(FechaHoraUTC, nullable=False)
    critico: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    visto_por: Mapped[str | None] = mapped_column(String(120))
    visto_en: Mapped[datetime | None] = mapped_column(FechaHoraUTC)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Cambio {self.campo}>"


class PerfilInteres(ModeloBase, Auditable):
    """RF-1.2: perfil de interes configurable desde la UI, nada hardcodeado.

    Puede haber varios perfiles activos (por ejemplo, uno por linea de negocio);
    una licitacion califica si calza con al menos uno.
    """

    __tablename__ = "perfiles_interes"
    __modulo_auditoria__ = "m1_radar"

    nombre: Mapped[str] = mapped_column(String(120), nullable=False)
    activo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    descripcion: Mapped[str | None] = mapped_column(Text)

    # Listas en JSON: se editan como listas en la UI y no justifican tablas
    # propias con este volumen.
    palabras_clave: Mapped[list | None] = mapped_column(JSON, default=list)
    palabras_excluidas: Mapped[list | None] = mapped_column(JSON, default=list)
    categorias_unspsc: Mapped[list | None] = mapped_column(JSON, default=list)
    regiones: Mapped[list | None] = mapped_column(JSON, default=list)
    comunas: Mapped[list | None] = mapped_column(JSON, default=list)
    tipos_licitacion: Mapped[list | None] = mapped_column(JSON, default=list)

    monto_minimo: Mapped[float | None] = mapped_column(Float)
    monto_maximo: Mapped[float | None] = mapped_column(Float)
    solo_obras: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Sobre este umbral, RF-2.2 encola la descarga automatica de anexos.
    umbral_interes: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<PerfilInteres {self.nombre} activo={self.activo}>"


class SincronizacionDia(Base):
    """Bitacora de dias ya sincronizados.

    Evita repetir una llamada ya hecha (RF-1.3) y permite detectar huecos: si
    falto un dia, se ve.
    """

    __tablename__ = "sincronizaciones_dia"
    __table_args__ = (UniqueConstraint("dia", name="uq_sincronizacion_dia"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    dia: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    ejecutado_en: Mapped[datetime] = mapped_column(FechaHoraUTC, nullable=False)
    total_api: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    nuevas: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    candidatas: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    detalles_pedidos: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    ok: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    error: Mapped[str | None] = mapped_column(Text)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<SincronizacionDia {self.dia} nuevas={self.nuevas}>"
